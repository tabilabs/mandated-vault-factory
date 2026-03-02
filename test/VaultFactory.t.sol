// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IVaultFactory} from "../src/interfaces/IVaultFactory.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";
import {MockAdapter, DrainAdapter, MockERC1271Authority, RejectingERC1271Authority} from "../src/mocks/MockAdapter.sol";
import {AdapterLib} from "../src/libs/AdapterLib.sol";
import {Initializable} from "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import {Errors} from "@openzeppelin/contracts/utils/Errors.sol";

/// @dev Simple ERC-20 with mint/burn for testing.
contract MockToken is ERC20 {
    constructor() ERC20("Mock Token", "MOCK") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }

    function burn(address from, uint256 amount) external {
        _burn(from, amount);
    }
}

contract VaultFactoryTest is Test {
    VaultFactory public factory;
    MockToken public token;
    MockAdapter public adapter;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);
    address internal depositor = address(0xD0);

    // Merkle helpers
    bytes32 internal adapterLeaf;
    bytes32 internal merkleRoot;

    function setUp() public {
        authority = vm.addr(authorityKey);
        token = new MockToken();
        factory = new VaultFactory();
        adapter = new MockAdapter();

        // Compute single-leaf Merkle root for adapter
        adapterLeaf = keccak256(abi.encode(address(adapter), address(adapter).codehash));
        merkleRoot = adapterLeaf;
    }

    // =========== Helper functions ===========

    function _createVault() internal returns (MandatedVaultClone vault) {
        vm.prank(creator);
        address v = factory.createVault(address(token), "Test Vault", "tVAULT", authority, bytes32(0));
        vault = MandatedVaultClone(payable(v));
    }

    function _defaultMandate(MandatedVaultClone vault, uint256 nonce)
        internal
        view
        returns (IERCXXXXMandatedVault.Mandate memory)
    {
        return IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: merkleRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
    }

    function _defaultActions() internal view returns (IERCXXXXMandatedVault.Action[] memory) {
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action({
            adapter: address(adapter), value: 0, data: abi.encodeCall(MockAdapter.doNothing, ())
        });
        return actions;
    }

    function _defaultProofs() internal pure returns (bytes32[][] memory) {
        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);
        return proofs;
    }

    function _signMandate(MandatedVaultClone vault, IERCXXXXMandatedVault.Mandate memory mandate)
        internal
        view
        returns (bytes memory)
    {
        bytes32 mandateHash = vault.hashMandate(mandate);
        (uint8 v, bytes32 r, bytes32 s) = vm.sign(authorityKey, mandateHash);
        return abi.encodePacked(r, s, v);
    }

    function _executeDefault(MandatedVaultClone vault, uint256 nonce) internal returns (uint256 pre, uint256 post) {
        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, nonce);
        IERCXXXXMandatedVault.Action[] memory actions = _defaultActions();
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        return vault.execute(mandate, actions, sig, _defaultProofs(), "");
    }

    // =========== Factory: Creation ===========

    function test_createVault() public {
        MandatedVaultClone vault = _createVault();

        assertTrue(factory.isVault(address(vault)), "vault should be registered");
        assertEq(factory.vaultCount(), 1, "vault count should be 1");
        assertEq(vault.mandateAuthority(), authority, "authority should match");
        assertEq(vault.asset(), address(token), "asset should match");
        assertEq(vault.name(), "Test Vault", "name should match");
        assertEq(vault.symbol(), "tVAULT", "symbol should match");
    }

    function test_createVault_emitsEvent() public {
        vm.prank(creator);
        vm.expectEmit(false, true, true, true);
        emit IVaultFactory.VaultCreated(address(0), creator, authority, address(token), "Test Vault", "tVAULT");

        factory.createVault(address(token), "Test Vault", "tVAULT", authority, bytes32(0));
    }

    function test_createMultipleVaults() public {
        vm.startPrank(creator);
        factory.createVault(address(token), "Vault A", "vA", authority, bytes32(uint256(1)));
        factory.createVault(address(token), "Vault B", "vB", authority, bytes32(uint256(2)));
        vm.stopPrank();

        address[] memory vaults = factory.getVaultsByCreator(creator);
        assertEq(vaults.length, 2, "creator should have 2 vaults");
        assertEq(factory.vaultCount(), 2, "vault count should be 2");
    }

    function test_createVault_revert_zeroAuthority() public {
        vm.prank(creator);
        vm.expectRevert(IERCXXXXMandatedVault.ZeroAddressAuthority.selector);
        factory.createVault(address(token), "V", "V", address(0), bytes32(0));
    }

    function test_createVault_revert_duplicateSalt() public {
        vm.startPrank(creator);
        factory.createVault(address(token), "V", "V", authority, bytes32(0));

        // Same params + same salt from same creator → CREATE2 collision
        vm.expectRevert(Errors.FailedDeployment.selector);
        factory.createVault(address(token), "V", "V", authority, bytes32(0));
        vm.stopPrank();
    }

    // =========== Factory: Address Prediction ===========

    function test_predictVaultAddress() public {
        vm.prank(creator);
        address predicted = factory.predictVaultAddress(address(token), "Test Vault", "tVAULT", authority, bytes32(0));

        MandatedVaultClone vault = _createVault();
        assertEq(address(vault), predicted, "predicted address should match actual");
    }

    // =========== Factory: Implementation ===========

    function test_implementation_isLocked() public {
        MandatedVaultClone impl = MandatedVaultClone(payable(factory.implementation()));

        vm.expectRevert(Initializable.InvalidInitialization.selector);
        impl.initialize(IERC20(address(token)), "X", "X", authority);
    }

    // =========== ERC-4626: Deposit & Withdraw ===========

    function test_depositAndWithdraw() public {
        MandatedVaultClone vault = _createVault();

        // Mint tokens to depositor and approve vault
        token.mint(depositor, 1000e18);
        vm.startPrank(depositor);
        token.approve(address(vault), 1000e18);

        uint256 shares = vault.deposit(500e18, depositor);
        assertGt(shares, 0, "should receive shares");
        assertEq(vault.totalAssets(), 500e18, "vault should hold 500 tokens");

        uint256 withdrawn = vault.withdraw(250e18, depositor, depositor);
        assertGt(withdrawn, 0, "should burn shares");
        assertEq(vault.totalAssets(), 250e18, "vault should hold 250 tokens after withdrawal");
        vm.stopPrank();
    }

    function test_mintAndRedeem() public {
        MandatedVaultClone vault = _createVault();

        token.mint(depositor, 1000e18);
        vm.startPrank(depositor);
        token.approve(address(vault), 1000e18);

        uint256 assets = vault.mint(100e18, depositor);
        assertGt(assets, 0, "should consume assets");

        uint256 assetsBack = vault.redeem(50e18, depositor, depositor);
        assertGt(assetsBack, 0, "should return assets");
        vm.stopPrank();
    }

    // =========== Mandate Execution ===========

    function test_basicExecution() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        (uint256 pre, uint256 post) = _executeDefault(vault, 0);
        assertEq(pre, post, "no-op adapter should not change totalAssets");
        assertTrue(vault.isNonceUsed(authority, 0), "nonce should be marked used");
    }

    function test_multipleExecutions() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        _executeDefault(vault, 0);
        _executeDefault(vault, 1);
        _executeDefault(vault, 2);
        assertTrue(vault.isNonceUsed(authority, 2));
    }

    // =========== Authority Management ===========

    function test_proposeAndAcceptAuthority() public {
        MandatedVaultClone vault = _createVault();
        address newAuth = address(0xBEEF);

        vm.prank(authority);
        vault.proposeAuthority(newAuth);
        assertEq(vault.pendingAuthority(), newAuth);

        vm.prank(newAuth);
        vault.acceptAuthority();
        assertEq(vault.mandateAuthority(), newAuth);
        assertEq(vault.pendingAuthority(), address(0));
    }

    function test_proposeAuthority_revert_notAuthority() public {
        MandatedVaultClone vault = _createVault();

        vm.prank(address(0xBAD));
        vm.expectRevert(IERCXXXXMandatedVault.NotAuthority.selector);
        vault.proposeAuthority(address(0xBEEF));
    }

    // =========== Revocation ===========

    function test_revokeMandate() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes32 mandateHash = vault.hashMandate(mandate);

        vm.prank(authority);
        vault.revokeMandate(mandateHash);
        assertTrue(vault.isMandateRevoked(mandateHash));

        bytes memory sig = _signMandate(vault, mandate);
        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.MandateIsRevoked.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    function test_invalidateNonce() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        vm.prank(authority);
        vault.invalidateNonce(0);
        assertTrue(vault.isNonceUsed(authority, 0));

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.NonceAlreadyUsed.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    function test_invalidateNoncesBelow() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        vm.prank(authority);
        vault.invalidateNoncesBelow(10);
        assertEq(vault.nonceThreshold(authority), 10);

        // Nonce 5 should be rejected
        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 5);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.NonceBelowThreshold.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    // =========== Epoch Management ===========

    function test_resetEpoch() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        // Execute once to initialize epoch
        _executeDefault(vault, 0);

        vm.prank(authority);
        vault.resetEpoch();

        assertEq(vault.epochAssets(), vault.totalAssets());
        assertEq(vault.epochStart(), uint48(block.timestamp));
    }

    // =========== Drawdown Circuit Breaker ===========

    function test_drawdownExceeded() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        DrainAdapter drainer = new DrainAdapter();
        bytes32 drainerRoot = keccak256(abi.encode(address(drainer), address(drainer).codehash));

        // Drain 10% (exceeds 5% max)
        _drainExpectRevert(vault, drainer, drainerRoot, 0, 100_000e18, IERCXXXXMandatedVault.DrawdownExceeded.selector);
    }

    // =========== Cross-Vault Isolation ===========

    function test_vaultsHaveIsolatedState() public {
        // Create two vaults for same creator
        vm.startPrank(creator);
        address v1 = factory.createVault(address(token), "Vault 1", "V1", authority, bytes32(uint256(1)));
        address v2 = factory.createVault(address(token), "Vault 2", "V2", authority, bytes32(uint256(2)));
        vm.stopPrank();

        MandatedVaultClone vault1 = MandatedVaultClone(payable(v1));
        MandatedVaultClone vault2 = MandatedVaultClone(payable(v2));

        // Fund vault1 only
        token.mint(v1, 1_000_000e18);

        // Execute on vault1
        _executeDefault(vault1, 0);

        // vault2 should have independent nonce state
        assertFalse(vault2.isNonceUsed(authority, 0), "vault2 nonce 0 should be unused");
        assertEq(vault2.totalAssets(), 0, "vault2 should have 0 assets");

        // Vault names should differ
        assertEq(vault1.name(), "Vault 1");
        assertEq(vault2.name(), "Vault 2");
    }

    function test_vaultsHaveIsolatedDomainSeparator() public {
        vm.startPrank(creator);
        address v1 = factory.createVault(address(token), "V1", "V1", authority, bytes32(uint256(1)));
        address v2 = factory.createVault(address(token), "V2", "V2", authority, bytes32(uint256(2)));
        vm.stopPrank();

        MandatedVaultClone vault1 = MandatedVaultClone(payable(v1));
        MandatedVaultClone vault2 = MandatedVaultClone(payable(v2));

        token.mint(v1, 1_000_000e18);
        token.mint(v2, 1_000_000e18);

        // Same mandate params but different domain separator → different hash
        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault1, 0);
        bytes32 hash1 = vault1.hashMandate(mandate);
        bytes32 hash2 = vault2.hashMandate(mandate);
        assertTrue(hash1 != hash2, "mandate hashes should differ across vaults");

        // Signature valid for vault1 should NOT work on vault2
        bytes memory sig = _signMandate(vault1, mandate);
        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidSignature.selector);
        vault2.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    // =========== Sweep Native ===========

    function test_sweepNative() public {
        MandatedVaultClone vault = _createVault();

        // Force-send ETH to vault
        vm.deal(address(vault), 1 ether);

        address payable recipient = payable(address(0xCAFE));
        vm.prank(authority);
        vault.sweepNative(recipient, 1 ether);
        assertEq(recipient.balance, 1 ether);
    }

    // =========== ERC-165 ===========

    function test_supportsInterface() public {
        MandatedVaultClone vault = _createVault();

        assertTrue(vault.supportsInterface(type(IERCXXXXMandatedVault).interfaceId));
    }

    // =========== Security Audit Fixes ===========

    function test_createVault_revert_zeroAsset() public {
        vm.prank(creator);
        vm.expectRevert(MandatedVaultClone.ZeroAddressAsset.selector);
        factory.createVault(address(0), "V", "V", authority, bytes32(0));
    }

    function test_sweepNative_revert_notAuthority() public {
        MandatedVaultClone vault = _createVault();
        vm.deal(address(vault), 1 ether);

        vm.prank(address(0xBAD));
        vm.expectRevert(IERCXXXXMandatedVault.NotAuthority.selector);
        vault.sweepNative(payable(address(0xCAFE)), 1 ether);
    }

    function test_sweepNative_revert_zeroAddress() public {
        MandatedVaultClone vault = _createVault();
        vm.deal(address(vault), 1 ether);

        vm.prank(authority);
        vm.expectRevert(MandatedVaultClone.ZeroAddressRecipient.selector);
        vault.sweepNative(payable(address(0)), 1 ether);
    }

    function test_predictVaultAddress_withCreator() public {
        // Use the overloaded version with explicit creator
        address predicted =
            factory.predictVaultAddress(creator, address(token), "Test Vault", "tVAULT", authority, bytes32(0));

        MandatedVaultClone vault = _createVault();
        assertEq(address(vault), predicted, "creator-parameterized prediction should match");
    }

    // =========== VaultBusy Guard ===========

    function test_vaultBusy_depositDuringExecute() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        DepositAttackAdapter attacker = new DepositAttackAdapter(address(vault), address(token));
        token.mint(address(attacker), 100e18);

        bytes memory revertData = _executeVaultBusyAttack(vault, attacker);

        // Verify outer ActionCallFailed and inner VaultBusy
        _assertVaultBusyRevert(revertData);
    }

    function _assertVaultBusyRevert(bytes memory revertData) internal pure {
        // Outer error: ActionCallFailed selector
        assertEq(bytes4(revertData), IERCXXXXMandatedVault.ActionCallFailed.selector);

        // Decode: skip 4-byte selector, then abi.decode(uint256, bytes)
        bytes memory payload = _sliceBytes(revertData, 4);
        (, bytes memory reason) = abi.decode(payload, (uint256, bytes));

        // Inner reason: VaultBusy selector
        assertGe(reason.length, 4);
        bytes4 inner;
        assembly {
            inner := mload(add(reason, 0x20))
        }
        assertEq(inner, IERCXXXXMandatedVault.VaultBusy.selector);
    }

    function _executeVaultBusyAttack(MandatedVaultClone vault, DepositAttackAdapter attacker)
        internal
        returns (bytes memory)
    {
        bytes32 leaf = keccak256(abi.encode(address(attacker), address(attacker).codehash));

        IERCXXXXMandatedVault.Mandate memory mandate = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: 0,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: leaf,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] =
            IERCXXXXMandatedVault.Action(address(attacker), 0, abi.encodeCall(DepositAttackAdapter.tryDeposit, ()));

        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        try vault.execute(mandate, actions, sig, proofs, "") {
            revert("expected revert");
        } catch (bytes memory rd) {
            return rd;
        }
    }

    function _sliceBytes(bytes memory data, uint256 start) internal pure returns (bytes memory) {
        uint256 len = data.length - start;
        bytes memory result = new bytes(len);
        for (uint256 i; i < len;) {
            result[i] = data[start + i];
            unchecked {
                ++i;
            }
        }
        return result;
    }

    // =========== Mandate Deadline ===========

    function test_mandateExpired() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        mandate.deadline = uint48(block.timestamp + 100);

        bytes memory sig = _signMandate(vault, mandate);

        // Warp past deadline
        vm.warp(block.timestamp + 101);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.MandateExpired.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    // =========== Authority Epoch Mismatch ===========

    function test_authorityEpochMismatch() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        // Sign mandate for epoch 0
        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        // Transfer authority (bumps epoch to 1)
        address newAuth = address(0xBEEF);
        vm.prank(authority);
        vault.proposeAuthority(newAuth);
        vm.prank(newAuth);
        vault.acceptAuthority();

        // Old mandate with epoch 0 should fail
        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.AuthorityEpochMismatch.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    // =========== Action Call Failure ===========

    function test_actionCallFailed() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action({
            adapter: address(adapter), value: 0, data: abi.encodeCall(MockAdapter.alwaysReverts, ())
        });

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectPartialRevert(IERCXXXXMandatedVault.ActionCallFailed.selector);
        vault.execute(mandate, actions, sig, _defaultProofs(), "");
    }

    // =========== Payload Digest Mismatch ===========

    function test_payloadDigestMismatch() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Action[] memory actions = _defaultActions();

        // Sign mandate with a WRONG payload digest
        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        mandate.payloadDigest = bytes32(uint256(1)); // wrong digest

        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.PayloadDigestMismatch.selector);
        vault.execute(mandate, actions, sig, _defaultProofs(), "");
    }

    // =========== Different Creators Same Params ===========

    function test_differentCreatorsSameParams() public {
        address creator2 = address(0xC1);

        vm.prank(creator);
        address v1 = factory.createVault(address(token), "V", "V", authority, bytes32(0));

        vm.prank(creator2);
        address v2 = factory.createVault(address(token), "V", "V", authority, bytes32(0));

        assertTrue(v1 != v2, "different creators should get different addresses");
        assertTrue(factory.isVault(v1));
        assertTrue(factory.isVault(v2));
    }
    // =========== ERC-1271 Smart Contract Authority ===========

    function test_erc1271_validSignature() public {
        MockERC1271Authority contractAuth = new MockERC1271Authority(vm.addr(authorityKey));

        vm.prank(creator);
        address v =
            factory.createVault(address(token), "ERC1271 Vault", "e1271V", address(contractAuth), bytes32(uint256(42)));
        MandatedVaultClone vault = MandatedVaultClone(payable(v));
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        (uint256 pre, uint256 post) = vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
        assertEq(pre, post, "no-op should not change assets");
        assertTrue(vault.isNonceUsed(address(contractAuth), 0), "nonce should be used");
    }

    function test_erc1271_rejectingAuthority() public {
        RejectingERC1271Authority rejectAuth = new RejectingERC1271Authority();

        vm.prank(creator);
        address v = factory.createVault(address(token), "Reject Vault", "rV", address(rejectAuth), bytes32(uint256(43)));
        MandatedVaultClone vault = MandatedVaultClone(payable(v));
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.InvalidSignature.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    // =========== Selector Allowlist Extension ===========

    function _buildSelectorExt(address adapterAddr, bytes4 selector_)
        internal
        pure
        returns (bytes memory extensions, bytes32 extensionsHash)
    {
        bytes32 selectorLeaf = keccak256(abi.encode(adapterAddr, selector_));
        bytes32[][] memory selectorProofs = new bytes32[][](1);
        selectorProofs[0] = new bytes32[](0);

        bytes4 selectorAllowlistId = bytes4(keccak256("erc-xxxx:selector-allowlist@v1"));

        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension({
            id: selectorAllowlistId, required: false, data: abi.encode(selectorLeaf, selectorProofs)
        });
        extensions = abi.encode(exts);
        extensionsHash = keccak256(extensions);
    }

    function test_selectorAllowlist_validExecution() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        (bytes memory extensions, bytes32 extensionsHash) =
            _buildSelectorExt(address(adapter), MockAdapter.doNothing.selector);

        IERCXXXXMandatedVault.Mandate memory mandate = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: 0,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: merkleRoot,
            payloadDigest: bytes32(0),
            extensionsHash: extensionsHash
        });

        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        (uint256 pre, uint256 post) = vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), extensions);
        assertEq(pre, post, "no-op with selector allowlist should succeed");
    }

    function test_selectorAllowlist_revert_wrongSelector() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        // Allowlist only permits alwaysReverts, but actions use doNothing
        (bytes memory extensions, bytes32 extensionsHash) =
            _buildSelectorExt(address(adapter), MockAdapter.alwaysReverts.selector);

        IERCXXXXMandatedVault.Mandate memory mandate = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: 0,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: merkleRoot,
            payloadDigest: bytes32(0),
            extensionsHash: extensionsHash
        });

        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectPartialRevert(AdapterLib.SelectorNotAllowed.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), extensions);
    }

    function test_supportsExtension_selectorAllowlist() public {
        MandatedVaultClone vault = _createVault();
        bytes4 selectorAllowlistId = bytes4(keccak256("erc-xxxx:selector-allowlist@v1"));
        assertTrue(vault.supportsExtension(selectorAllowlistId), "should support selector allowlist");
        assertFalse(vault.supportsExtension(bytes4(0xdeadbeef)), "should not support random extension");
    }

    // =========== Cumulative Drawdown ===========

    function _drainExecute(
        MandatedVaultClone vault,
        DrainAdapter drainer,
        bytes32 drainerRoot,
        uint256 nonce,
        uint256 drainAmt
    ) internal returns (uint256 pre, uint256 post) {
        IERCXXXXMandatedVault.Mandate memory mandate = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: drainerRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action({
            adapter: address(drainer),
            value: 0,
            data: abi.encodeCall(DrainAdapter.drain, (address(token), address(vault), drainAmt))
        });
        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        return vault.execute(mandate, actions, sig, proofs, "");
    }

    function _drainExpectRevert(
        MandatedVaultClone vault,
        DrainAdapter drainer,
        bytes32 drainerRoot,
        uint256 nonce,
        uint256 drainAmt,
        bytes4 expectedError
    ) internal {
        IERCXXXXMandatedVault.Mandate memory mandate = IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: drainerRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action({
            adapter: address(drainer),
            value: 0,
            data: abi.encodeCall(DrainAdapter.drain, (address(token), address(vault), drainAmt))
        });
        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(expectedError);
        vault.execute(mandate, actions, sig, proofs, "");
    }

    function test_cumulativeDrawdownExceeded() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        DrainAdapter drainer = new DrainAdapter();
        bytes32 drainerRoot = keccak256(abi.encode(address(drainer), address(drainer).codehash));

        // First execution: drain 4% (under 5% single max, under 10% cumulative max)
        (uint256 pre1, uint256 post1) = _drainExecute(vault, drainer, drainerRoot, 0, 40_000e18);
        assertEq(pre1, 1_000_000e18);
        assertEq(post1, 960_000e18);

        // Second execution: drain ~4.5% of current → cumulative 8.32% (under 10%)
        (uint256 pre2, uint256 post2) = _drainExecute(vault, drainer, drainerRoot, 1, 43_200e18);
        assertEq(pre2, 960_000e18);
        assertEq(post2, 916_800e18);

        // Third execution: drain ~4% of current → cumulative 11.9% > 10% → revert
        _drainExpectRevert(
            vault, drainer, drainerRoot, 2, 36_672e18, IERCXXXXMandatedVault.CumulativeDrawdownExceeded.selector
        );
    }

    // =========== Multi-Action Execution ===========

    function test_multiActionExecution() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        // 3 actions all calling doNothing on the same adapter
        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](3);
        for (uint256 i = 0; i < 3; i++) {
            actions[i] = IERCXXXXMandatedVault.Action({
                adapter: address(adapter), value: 0, data: abi.encodeCall(MockAdapter.doNothing, ())
            });
        }

        bytes32[][] memory proofs = new bytes32[][](3);
        for (uint256 i = 0; i < 3; i++) {
            proofs[i] = new bytes32[](0);
        }

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        (uint256 pre, uint256 post) = vault.execute(mandate, actions, sig, proofs, "");
        assertEq(pre, post, "multi no-op should not change assets");
    }

    // =========== Edge Case: Empty Actions ===========

    function test_emptyActions_revert() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](0);
        bytes32[][] memory proofs = new bytes32[][](0);

        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.EmptyActions.selector);
        vault.execute(mandate, actions, sig, proofs, "");
    }

    // =========== Unbounded Open Mandate ===========

    function test_unboundedOpenMandate_revert() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        // executor=0 AND payloadDigest=0 → unbounded open mandate
        IERCXXXXMandatedVault.Mandate memory mandate = IERCXXXXMandatedVault.Mandate({
            executor: address(0),
            nonce: 0,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: merkleRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });

        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.UnboundedOpenMandate.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    // =========== Open Mandate (executor=0, payloadDigest!=0) ===========

    function test_openMandate_anyoneCanExecute() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        IERCXXXXMandatedVault.Action[] memory actions = _defaultActions();
        bytes32 actionsDigest = keccak256(abi.encode(actions));

        // executor=0 but payloadDigest is bound → valid open mandate
        IERCXXXXMandatedVault.Mandate memory mandate = IERCXXXXMandatedVault.Mandate({
            executor: address(0),
            nonce: 0,
            deadline: 0,
            authorityEpoch: vault.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: merkleRoot,
            payloadDigest: actionsDigest,
            extensionsHash: keccak256("")
        });

        bytes memory sig = _signMandate(vault, mandate);

        // Random address can execute (not just the designated executor)
        address randomCaller = address(0xFACE);
        vm.prank(randomCaller);
        (uint256 pre, uint256 post) = vault.execute(mandate, actions, sig, _defaultProofs(), "");
        assertEq(pre, post, "open mandate no-op should succeed");
    }

    // =========== Nonce Replay Protection ===========

    function test_nonceReplay_revert() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        _executeDefault(vault, 0);

        // Try to replay the same nonce
        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.NonceAlreadyUsed.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), "");
    }

    // =========== Threshold Not Increased ===========

    function test_thresholdNotIncreased_revert() public {
        MandatedVaultClone vault = _createVault();

        vm.startPrank(authority);
        vault.invalidateNoncesBelow(10);

        vm.expectRevert(IERCXXXXMandatedVault.ThresholdNotIncreased.selector);
        vault.invalidateNoncesBelow(5);

        vm.expectRevert(IERCXXXXMandatedVault.ThresholdNotIncreased.selector);
        vault.invalidateNoncesBelow(10);
        vm.stopPrank();
    }

    // =========== Extensions Hash Mismatch ===========

    function test_extensionsHashMismatch_revert() public {
        MandatedVaultClone vault = _createVault();
        token.mint(address(vault), 1_000_000e18);

        // Mandate says extensionsHash = keccak256(""), but we pass non-empty extensions
        IERCXXXXMandatedVault.Mandate memory mandate = _defaultMandate(vault, 0);
        bytes memory sig = _signMandate(vault, mandate);

        bytes memory wrongExtensions = hex"deadbeef";

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.ExtensionsHashMismatch.selector);
        vault.execute(mandate, _defaultActions(), sig, _defaultProofs(), wrongExtensions);
    }
}

/// @dev Adapter that attempts to deposit into vault during execute (VaultBusy test).
contract DepositAttackAdapter {
    address public vault;
    address public token;

    constructor(address vault_, address token_) {
        vault = vault_;
        token = token_;
    }

    function tryDeposit() external {
        IERC20(token).approve(vault, 100e18);
        // This should revert with VaultBusy
        MandatedVaultClone(payable(vault)).deposit(100e18, address(this));
    }

    receive() external payable {}
}
