// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";
import {MockAdapter, DrainAdapter} from "../src/mocks/MockAdapter.sol";
import {AuthorityHijackAdapter} from "../src/mocks/MockAdapter.sol";
import {LargeRevertAdapter} from "../src/mocks/MockAdapter.sol";
import {ShortReturnAuthority} from "../src/mocks/MockAdapter.sol";
import {AdapterLib} from "../src/libs/AdapterLib.sol";
import {MandateLib} from "../src/libs/MandateLib.sol";

/// @dev Simple ERC-20 for testing.
contract BranchMockToken is ERC20 {
    constructor() ERC20("Branch Mock", "BMOCK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external {
        _burn(from, amount);
    }
}

/// @dev Contract that rejects ETH transfers.
contract RejectETH {}

/// @title VaultBranchTest
/// @notice Defensive branch coverage tests for revert paths in libraries and edge cases.
/// @dev Struct construction delegated to helpers to avoid "stack too deep" under
///      forge coverage --ir-minimum. All vm.expectRevert calls are placed AFTER
///      sig computation to avoid intercepting v.hashMandate() view calls.
contract VaultBranchTest is Test {
    VaultFactory public factory;
    BranchMockToken public token;
    MockAdapter public adapter;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);

    bytes32 internal merkleRoot;

    function setUp() public {
        authority = vm.addr(authorityKey);
        token = new BranchMockToken();
        factory = new VaultFactory();
        adapter = new MockAdapter();
        merkleRoot = keccak256(abi.encode(address(adapter), address(adapter).codehash));
    }

    // ─── Helpers ────────────────────────────────────────────────────

    function _vault() internal returns (MandatedVaultClone v) {
        vm.prank(creator);
        v = MandatedVaultClone(payable(factory.createVault(address(token), "BV", "BV", authority, bytes32(0))));
        token.mint(address(v), 1_000_000e18);
    }

    function _mandate(MandatedVaultClone v, uint256 nonce)
        internal
        view
        returns (IERCXXXXMandatedVault.Mandate memory)
    {
        return IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: merkleRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
    }

    function _sign(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m) internal view returns (bytes memory) {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(authorityKey, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    function _actions() internal view returns (IERCXXXXMandatedVault.Action[] memory a) {
        a = new IERCXXXXMandatedVault.Action[](1);
        a[0] = IERCXXXXMandatedVault.Action(address(adapter), 0, abi.encodeCall(MockAdapter.doNothing, ()));
    }

    function _proofs() internal pure returns (bytes32[][] memory p) {
        p = new bytes32[][](1);
        p[0] = new bytes32[](0);
    }

    // ─── P0-3: MandateLib branch tests ──────────────────────────────

    function test_unauthorizedExecutor_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        bytes memory sig = _sign(v, m);

        vm.prank(address(0xBAD));
        vm.expectRevert(IERCXXXXMandatedVault.UnauthorizedExecutor.selector);
        v.execute(m, _actions(), sig, _proofs(), "");
    }

    function test_invalidDrawdownBps_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.maxDrawdownBps = 10_001;
        m.maxCumulativeDrawdownBps = 10_001;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidDrawdownBps.selector);
        v.execute(m, _actions(), sig, _proofs(), "");
    }

    function test_invalidCumulativeDrawdownBps_lessThanSingle_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.maxDrawdownBps = 500;
        m.maxCumulativeDrawdownBps = 400;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidCumulativeDrawdownBps.selector);
        v.execute(m, _actions(), sig, _proofs(), "");
    }

    function test_invalidAdaptersRoot_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.allowedAdaptersRoot = bytes32(0);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidAdaptersRoot.selector);
        v.execute(m, _actions(), sig, _proofs(), "");
    }

    function test_tooManyActions_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        bytes memory sig = _sign(v, m);
        (IERCXXXXMandatedVault.Action[] memory acts, bytes32[][] memory proofs) = _buildManyActions(33);

        vm.prank(executor);
        vm.expectPartialRevert(MandateLib.TooManyActions.selector);
        v.execute(m, acts, sig, proofs, "");
    }

    function _buildManyActions(uint256 count)
        internal
        view
        returns (IERCXXXXMandatedVault.Action[] memory acts, bytes32[][] memory proofs)
    {
        acts = new IERCXXXXMandatedVault.Action[](count);
        proofs = new bytes32[][](count);
        for (uint256 i = 0; i < count; i++) {
            acts[i] = IERCXXXXMandatedVault.Action(address(adapter), 0, abi.encodeCall(MockAdapter.doNothing, ()));
            proofs[i] = new bytes32[](0);
        }
    }

    // ─── P0-3: AdapterLib branch tests ──────────────────────────────

    function test_nonZeroActionValue_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        bytes memory sig = _sign(v, m);

        IERCXXXXMandatedVault.Action[] memory acts = new IERCXXXXMandatedVault.Action[](1);
        acts[0] = IERCXXXXMandatedVault.Action(address(adapter), 1, abi.encodeCall(MockAdapter.doNothing, ()));

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.NonZeroActionValue.selector);
        v.execute(m, acts, sig, _proofs(), "");
    }

    function test_adapterNotAllowed_wrongAdapter_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        bytes memory sig = _sign(v, m);

        DrainAdapter wrong = new DrainAdapter();
        IERCXXXXMandatedVault.Action[] memory acts = new IERCXXXXMandatedVault.Action[](1);
        acts[0] = IERCXXXXMandatedVault.Action(address(wrong), 0, abi.encodeCall(MockAdapter.doNothing, ()));

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.AdapterNotAllowed.selector);
        v.execute(m, acts, sig, _proofs(), "");
    }

    function test_adapterProofsMismatch_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        bytes memory sig = _sign(v, m);

        bytes32[][] memory wrongP = new bytes32[][](2);
        wrongP[0] = new bytes32[](0);
        wrongP[1] = new bytes32[](0);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.AdapterNotAllowed.selector);
        v.execute(m, _actions(), sig, wrongP, "");
    }

    function test_adapterProofTooDeep_revert() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        bytes memory sig = _sign(v, m);

        bytes32[][] memory deep = new bytes32[][](1);
        deep[0] = new bytes32[](65);

        vm.prank(executor);
        vm.expectPartialRevert(AdapterLib.AdapterProofTooDeep.selector);
        v.execute(m, _actions(), sig, deep, "");
    }

    // ─── P0-3: Extension branch tests ───────────────────────────────

    function test_invalidExtensionsEncoding_revert() public {
        MandatedVaultClone v = _vault();
        bytes memory bad = hex"deadbeefcafebabe0000000000000000";
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = keccak256(bad);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidExtensionsEncoding.selector);
        v.execute(m, _actions(), sig, _proofs(), bad);
    }

    function test_unsupportedRequiredExtension_revert() public {
        MandatedVaultClone v = _vault();
        (bytes memory ext, bytes32 hash) = _buildRequiredUnknownExt();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = hash;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(IERCXXXXMandatedVault.UnsupportedRequiredExtension.selector);
        v.execute(m, _actions(), sig, _proofs(), ext);
    }

    function _buildRequiredUnknownExt() internal pure returns (bytes memory ext, bytes32 hash) {
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(0xdeadbeef), true, "");
        ext = abi.encode(exts);
        hash = keccak256(ext);
    }

    function test_extensionsNotCanonical_revert() public {
        MandatedVaultClone v = _vault();
        (bytes memory ext, bytes32 hash) = _buildNonCanonicalExt();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = hash;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.ExtensionsNotCanonical.selector);
        v.execute(m, _actions(), sig, _proofs(), ext);
    }

    function _buildNonCanonicalExt() internal pure returns (bytes memory ext, bytes32 hash) {
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](2);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(0xbbbbbbbb), false, "");
        exts[1] = IERCXXXXMandatedVault.Extension(bytes4(0xaaaaaaaa), false, "");
        ext = abi.encode(exts);
        hash = keccak256(ext);
    }

    function test_tooManyExtensions_revert() public {
        MandatedVaultClone v = _vault();
        (bytes memory ext, bytes32 hash) = _buildTooManyExt();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = hash;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(MandatedVaultClone.TooManyExtensions.selector);
        v.execute(m, _actions(), sig, _proofs(), ext);
    }

    function _buildTooManyExt() internal pure returns (bytes memory ext, bytes32 hash) {
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](17);
        for (uint256 i = 0; i < 17; i++) {
            exts[i] = IERCXXXXMandatedVault.Extension(bytes4(uint32(i + 1)), false, "");
        }
        ext = abi.encode(exts);
        hash = keccak256(ext);
    }

    function test_extensionsTooLarge_revert() public {
        MandatedVaultClone v = _vault();
        (bytes memory big, bytes32 hash) = _buildOversizedExt();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = hash;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(MandateLib.ExtensionsTooLarge.selector);
        v.execute(m, _actions(), sig, _proofs(), big);
    }

    function _buildOversizedExt() internal pure returns (bytes memory data, bytes32 hash) {
        data = new bytes(131_073);
        hash = keccak256(data);
    }

    // ─── P1: Selector allowlist edge cases ──────────────────────────

    function test_selectorProofTooDeep_revert() public {
        MandatedVaultClone v = _vault();
        (bytes memory ext, bytes32 hash) = _buildDeepSelectorProofExt();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = hash;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(AdapterLib.SelectorProofTooDeep.selector);
        v.execute(m, _actions(), sig, _proofs(), ext);
    }

    function _buildDeepSelectorProofExt() internal view returns (bytes memory ext, bytes32 hash) {
        bytes32 leaf = keccak256(abi.encode(address(adapter), MockAdapter.doNothing.selector));
        bytes32[][] memory sp = new bytes32[][](1);
        sp[0] = new bytes32[](65);
        bytes memory data = abi.encode(leaf, sp);
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(keccak256("erc-xxxx:selector-allowlist@v1")), false, data);
        ext = abi.encode(exts);
        hash = keccak256(ext);
    }

    function test_invalidActionData_revert() public {
        MandatedVaultClone v = _vault();
        (bytes memory ext, bytes32 hash) = _buildDummySelectorExt();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = hash;
        bytes memory sig = _sign(v, m);

        IERCXXXXMandatedVault.Action[] memory acts = new IERCXXXXMandatedVault.Action[](1);
        acts[0] = IERCXXXXMandatedVault.Action(address(adapter), 0, hex"aabb");

        vm.prank(executor);
        vm.expectPartialRevert(AdapterLib.InvalidActionData.selector);
        v.execute(m, acts, sig, _proofs(), ext);
    }

    function _buildDummySelectorExt() internal pure returns (bytes memory ext, bytes32 hash) {
        bytes32 root = keccak256("dummy");
        bytes32[][] memory sp = new bytes32[][](1);
        sp[0] = new bytes32[](0);
        bytes memory data = abi.encode(root, sp);
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(keccak256("erc-xxxx:selector-allowlist@v1")), false, data);
        ext = abi.encode(exts);
        hash = keccak256(ext);
    }

    // ─── P1: Sweep failure ──────────────────────────────────────────

    function test_nativeSweepFailed_revert() public {
        MandatedVaultClone v = _vault();
        vm.deal(address(v), 1 ether);
        RejectETH r = new RejectETH();

        vm.prank(authority);
        vm.expectRevert(MandatedVaultClone.NativeSweepFailed.selector);
        v.sweepNative(payable(address(r)), 1 ether);
    }

    // --- P1 Regression: authority cache in MandateExecuted event --------------

    function test_mandateExecuted_logsPreExecutionAuthority() public {
        // Deploy hijack adapter and build its Merkle leaf
        AuthorityHijackAdapter hijack = new AuthorityHijackAdapter();
        bytes32 hijackRoot = keccak256(abi.encode(address(hijack), address(hijack).codehash));

        // Create vault with original authority
        vm.prank(creator);
        MandatedVaultClone v =
            MandatedVaultClone(payable(factory.createVault(address(token), "AV", "AV", authority, bytes32("auth"))));
        token.mint(address(v), 1_000_000e18);

        // Set hijack adapter as pendingAuthority
        vm.prank(authority);
        v.proposeAuthority(address(hijack));

        // Build mandate using hijack adapter
        IERCXXXXMandatedVault.Mandate memory m = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: 0,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: hijackRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });

        // Sign and build action that triggers acceptAuthority via adapter
        bytes memory sig = _signWith(v, m, authorityKey);
        IERCXXXXMandatedVault.Action[] memory acts = new IERCXXXXMandatedVault.Action[](1);
        acts[0] = IERCXXXXMandatedVault.Action(
            address(hijack), 0, abi.encodeCall(AuthorityHijackAdapter.hijackAuthority, (address(v)))
        );
        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);

        // Expect MandateExecuted with correct mandateHash topic + ORIGINAL authority
        bytes32 expectedMandateHash = v.hashMandate(m);
        vm.expectEmit(true, true, true, false, address(v));
        emit IERCXXXXMandatedVault.MandateExecuted(expectedMandateHash, authority, executor, bytes32(0), 0, 0);

        vm.prank(executor);
        v.execute(m, acts, sig, proofs, "");

        // Verify authority actually changed (hijack succeeded)
        assertEq(v.mandateAuthority(), address(hijack), "authority should have changed");
    }

    function _signWith(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m, uint256 key)
        internal
        view
        returns (bytes memory)
    {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(key, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    // --- P1 Regression: returndata truncation at 4 KiB -----------------------

    function test_actionCallFailed_returndataCappedAt4KiB() public {
        LargeRevertAdapter largeRev = new LargeRevertAdapter();
        bytes32 largeRoot = keccak256(abi.encode(address(largeRev), address(largeRev).codehash));

        vm.prank(creator);
        MandatedVaultClone v =
            MandatedVaultClone(payable(factory.createVault(address(token), "RV", "RV", authority, bytes32("ret"))));
        token.mint(address(v), 1_000_000e18);

        IERCXXXXMandatedVault.Mandate memory m = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: 0,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: largeRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });

        bytes memory sig = _signWith(v, m, authorityKey);
        IERCXXXXMandatedVault.Action[] memory acts = new IERCXXXXMandatedVault.Action[](1);
        acts[0] = IERCXXXXMandatedVault.Action(address(largeRev), 0, abi.encodeCall(LargeRevertAdapter.revertLarge, ()));
        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);

        vm.prank(executor);
        try v.execute(m, acts, sig, proofs, "") {
            revert("should have reverted");
        } catch (bytes memory revertData) {
            // Verify selector
            assertGt(revertData.length, 4, "revert data too short");
            assertEq(bytes4(revertData), IERCXXXXMandatedVault.ActionCallFailed.selector, "wrong selector");

            // Strip selector and decode payload
            (uint256 index, bytes memory reason) = abi.decode(_stripSelector(revertData), (uint256, bytes));
            assertEq(index, 0, "action index should be 0");
            assertEq(reason.length, 4096, "returndata should be exactly 4 KiB (adapter returns 8 KiB)");
        }
    }

    // --- P3: Edge case coverage improvements -----------------------------------

    function test_deadlineExactBoundary_succeeds() public {
        MandatedVaultClone v = _vault();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.deadline = uint48(block.timestamp + 100);
        bytes memory sig = _sign(v, m);

        vm.warp(block.timestamp + 100);

        vm.prank(executor);
        (uint256 pre, uint256 post) = v.execute(m, _actions(), sig, _proofs(), "");
        assertEq(pre, post, "should succeed at exact deadline");
    }

    function test_zeroAssets_drawdownSkipped() public {
        vm.prank(creator);
        MandatedVaultClone v =
            MandatedVaultClone(payable(factory.createVault(address(token), "ZV", "ZV", authority, bytes32("zero"))));

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        (uint256 pre, uint256 post) = v.execute(m, _actions(), sig, _proofs(), "");
        assertEq(pre, 0, "preAssets should be 0");
        assertEq(post, 0, "postAssets should be 0");
    }

    function test_zeroDrawdownBps_anyLossReverts() public {
        MandatedVaultClone v = _vault();
        DrainAdapter drainer = new DrainAdapter();
        bytes32 drainerRoot = keccak256(abi.encode(address(drainer), address(drainer).codehash));

        IERCXXXXMandatedVault.Mandate memory m = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: 0,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 0,
            maxCumulativeDrawdownBps: 0,
            allowedAdaptersRoot: drainerRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
        bytes memory sig = _sign(v, m);

        IERCXXXXMandatedVault.Action[] memory acts = new IERCXXXXMandatedVault.Action[](1);
        acts[0] = IERCXXXXMandatedVault.Action(
            address(drainer), 0, abi.encodeCall(DrainAdapter.drain, (address(token), address(v), 1e18))
        );
        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.DrawdownExceeded.selector);
        v.execute(m, acts, sig, proofs, "");
    }

    function test_selectorProofsLengthMismatch_revert() public {
        MandatedVaultClone v = _vault();
        (bytes memory ext, bytes32 hash) = _buildSelectorProofsMismatchExt();
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0);
        m.extensionsHash = hash;
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidExtensionsEncoding.selector);
        v.execute(m, _actions(), sig, _proofs(), ext);
    }

    function _buildSelectorProofsMismatchExt() internal pure returns (bytes memory ext, bytes32 hash) {
        bytes32 root = keccak256("dummy-root");
        bytes32[][] memory sp = new bytes32[][](2);
        sp[0] = new bytes32[](0);
        sp[1] = new bytes32[](0);
        bytes memory data = abi.encode(root, sp);
        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(keccak256("erc-xxxx:selector-allowlist@v1")), false, data);
        ext = abi.encode(exts);
        hash = keccak256(ext);
    }

    // --- P2: ERC-1271 short return data defense --------------------------------

    function test_erc1271_shortReturnData_revert() public {
        ShortReturnAuthority shortAuth = new ShortReturnAuthority();

        vm.prank(creator);
        MandatedVaultClone v = MandatedVaultClone(
            payable(factory.createVault(address(token), "SV", "SV", address(shortAuth), bytes32("short")))
        );
        token.mint(address(v), 1_000_000e18);

        IERCXXXXMandatedVault.Mandate memory m = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: 0,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: merkleRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });

        bytes memory sig = _signWith(v, m, authorityKey);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidSignature.selector);
        v.execute(m, _actions(), sig, _proofs(), "");
    }

    // --- Helpers (shared) -------------------------------------------------------

    /// @dev Strips the 4-byte selector from ABI-encoded revert data, returning the payload.
    function _stripSelector(bytes memory data) internal pure returns (bytes memory payload) {
        payload = new bytes(data.length - 4);
        for (uint256 i = 0; i < payload.length; i++) {
            payload[i] = data[i + 4];
        }
    }
}
