// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";

import {BSC_CHAIN_ID, BSC_BUSD} from "./helpers/BscForkConstants.sol";
import {MerkleHelper} from "./helpers/MerkleHelper.sol";

contract CoreNoopAdapter {
    function nop() external {}
}

contract CoreVaultBusyAdapter {
    address public immutable vault;

    constructor(address vault_) {
        vault = vault_;
    }

    function reenterDeposit(uint256 assets, address receiver) external {
        MandatedVaultClone(payable(vault)).deposit(assets, receiver);
    }

    function reenterWithdraw(uint256 assets, address receiver, address owner) external {
        MandatedVaultClone(payable(vault)).withdraw(assets, receiver, owner);
    }
}

contract VaultForkBscCoreSemanticsTest is Test {
    VaultFactory internal factory;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);

    uint256 internal nonceCounter;

    CoreNoopAdapter internal noopAdapter;

    function setUp() public {
        bool hasFork;
        try vm.activeFork() {
            hasFork = true;
        } catch {
            hasFork = false;
        }

        if (!hasFork) {
            vm.skip(true, "fork disabled: run with --fork-url");
            return;
        }

        if (block.chainid != BSC_CHAIN_ID) {
            vm.skip(true, "unexpected chainid: expected BSC testnet fork");
            return;
        }

        assertGt(BSC_BUSD.code.length, 0, "BUSD missing code");

        authority = vm.addr(authorityKey);
        factory = new VaultFactory();
        noopAdapter = new CoreNoopAdapter();
    }

    function test_bscFork_us01_factoryDeterministicPredict_withCreator_matchesCreate_andDifferentCreatorDiffers()
        public
    {
        bytes32 salt = keccak256("US01_SALT");
        address creatorA = address(0xCA01);
        address creatorB = address(0xCA02);

        string memory name = "Core Sem Vault";
        string memory symbol = "csv";

        address predictedA = factory.predictVaultAddress(creatorA, BSC_BUSD, name, symbol, authority, salt);
        address predictedB = factory.predictVaultAddress(creatorB, BSC_BUSD, name, symbol, authority, salt);

        assertTrue(predictedA != predictedB, "different creators should have different predictions");

        vm.prank(creatorA);
        address createdA = factory.createVault(BSC_BUSD, name, symbol, authority, salt);
        assertEq(createdA, predictedA, "predictedA should match createdA");

        vm.prank(creatorB);
        address createdB = factory.createVault(BSC_BUSD, name, symbol, authority, salt);
        assertEq(createdB, predictedB, "predictedB should match createdB");
    }

    function test_bscFork_us02b_vaultBusy_reenterDeposit_wrappedAsActionCallFailed_index1() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US02B_DEPOSIT"));
        CoreVaultBusyAdapter busyAdapter = new CoreVaultBusyAdapter(address(vault));

        (bytes32 root, bytes32[] memory proofNoop, bytes32[] memory proofBusy) =
            MerkleHelper.buildTree2(_leaf(address(noopAdapter)), _leaf(address(busyAdapter)));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(CoreNoopAdapter.nop, ()));
        actions[1] = IERCXXXXMandatedVault.Action(
            address(busyAdapter), 0, abi.encodeCall(CoreVaultBusyAdapter.reenterDeposit, (1, address(busyAdapter)))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = proofNoop;
        proofs[1] = proofBusy;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(vault, executor, _nextNonce(), root, bytes32(0));
        bytes memory sig = _sign(vault, m, authorityKey);

        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, sig, proofs, executor);
        assertTrue(!ok, "expected revert");
        assertEq(_revertSelector(ret), IERCXXXXMandatedVault.ActionCallFailed.selector, "expected ActionCallFailed");

        (uint256 index, bytes memory reason) = _decodeActionCallFailed(ret);
        assertEq(index, 1, "expected failing action index=1");
        assertEq(_revertSelector(reason), IERCXXXXMandatedVault.VaultBusy.selector, "inner reason should be VaultBusy");
    }

    function test_bscFork_us02b_vaultBusy_reenterWithdraw_wrappedAsActionCallFailed_index1() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US02B_WITHDRAW"));
        CoreVaultBusyAdapter busyAdapter = new CoreVaultBusyAdapter(address(vault));

        (bytes32 root, bytes32[] memory proofNoop, bytes32[] memory proofBusy) =
            MerkleHelper.buildTree2(_leaf(address(noopAdapter)), _leaf(address(busyAdapter)));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(CoreNoopAdapter.nop, ()));
        actions[1] = IERCXXXXMandatedVault.Action(
            address(busyAdapter),
            0,
            abi.encodeCall(CoreVaultBusyAdapter.reenterWithdraw, (1, address(busyAdapter), address(busyAdapter)))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = proofNoop;
        proofs[1] = proofBusy;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(vault, executor, _nextNonce(), root, bytes32(0));
        bytes memory sig = _sign(vault, m, authorityKey);

        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, sig, proofs, executor);
        assertTrue(!ok, "expected revert");
        assertEq(_revertSelector(ret), IERCXXXXMandatedVault.ActionCallFailed.selector, "expected ActionCallFailed");

        (uint256 index, bytes memory reason) = _decodeActionCallFailed(ret);
        assertEq(index, 1, "expected failing action index=1");
        assertEq(_revertSelector(reason), IERCXXXXMandatedVault.VaultBusy.selector, "inner reason should be VaultBusy");
    }

    function test_bscFork_us03a_unauthorizedExecutor_revertsDirect() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US03A"));

        bytes32 root = _leaf(address(noopAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(CoreNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        IERCXXXXMandatedVault.Mandate memory m = _mandate(vault, executor, _nextNonce(), root, bytes32(0));
        bytes memory sig = _sign(vault, m, authorityKey);

        address unauthorizedCaller = address(0xBAD);
        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, sig, proofs, unauthorizedCaller);

        assertTrue(!ok, "expected revert");
        bytes4 sel = _revertSelector(ret);
        assertEq(sel, IERCXXXXMandatedVault.UnauthorizedExecutor.selector, "unexpected selector");
        assertTrue(sel != IERCXXXXMandatedVault.ActionCallFailed.selector, "must be direct vault revert");
    }

    function test_bscFork_us03b_invalidSignature_revertsDirect() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US03B"));

        bytes32 root = _leaf(address(noopAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(CoreNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        IERCXXXXMandatedVault.Mandate memory m = _mandate(vault, executor, _nextNonce(), root, bytes32(0));
        bytes memory wrongSig = _sign(vault, m, 0xB0B);

        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, wrongSig, proofs, executor);

        assertTrue(!ok, "expected revert");
        bytes4 sel = _revertSelector(ret);
        assertEq(sel, IERCXXXXMandatedVault.InvalidSignature.selector, "unexpected selector");
        assertTrue(sel != IERCXXXXMandatedVault.ActionCallFailed.selector, "must be direct vault revert");
    }

    function test_bscFork_us03c_payloadDigestMismatch_revertsDirect() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US03C"));

        bytes32 root = _leaf(address(noopAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(CoreNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        // payloadDigest must bind to actionsDigest. Intentionally provide a wrong digest to trigger PayloadDigestMismatch.
        bytes32 wrongPayloadDigest = keccak256("US03C_WRONG_PAYLOAD_DIGEST");
        IERCXXXXMandatedVault.Mandate memory m = _mandate(vault, executor, _nextNonce(), root, wrongPayloadDigest);
        bytes memory sig = _sign(vault, m, authorityKey);

        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, sig, proofs, executor);

        assertTrue(!ok, "expected revert");
        bytes4 sel = _revertSelector(ret);
        assertEq(sel, IERCXXXXMandatedVault.PayloadDigestMismatch.selector, "unexpected selector");
        assertTrue(sel != IERCXXXXMandatedVault.ActionCallFailed.selector, "must be direct vault revert");
    }

    function test_bscFork_us04_allowlist_adapterNotAllowed_eoaOrEmptyAccount() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US04_EOA"));

        address eoa = address(0x12345);

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action({adapter: eoa, value: 0, data: hex"12345678"});

        bytes32[][] memory proofs = _singleEmptyProof();

        IERCXXXXMandatedVault.Mandate memory m = _mandate(
            vault,
            executor,
            _nextNonce(),
            bytes32(uint256(1)), // Non-zero root to avoid triggering InvalidAdaptersRoot.
            bytes32(0)
        );
        bytes memory sig = _sign(vault, m, authorityKey);

        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, sig, proofs, executor);

        assertTrue(!ok, "expected revert");
        assertEq(_revertSelector(ret), IERCXXXXMandatedVault.AdapterNotAllowed.selector, "unexpected selector");
    }

    function test_bscFork_us04_allowlist_adapterNotAllowed_leafMismatch() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US04_MISMATCH"));

        CoreNoopAdapter actualAdapter = new CoreNoopAdapter();
        CoreNoopAdapter allowedAdapter = new CoreNoopAdapter();

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(actualAdapter), 0, abi.encodeCall(CoreNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        // The root only allows allowedAdapter while the action uses actualAdapter, so the leaf/proof must mismatch.
        bytes32 root = _leaf(address(allowedAdapter));
        IERCXXXXMandatedVault.Mandate memory m = _mandate(vault, executor, _nextNonce(), root, bytes32(0));
        bytes memory sig = _sign(vault, m, authorityKey);

        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, sig, proofs, executor);

        assertTrue(!ok, "expected revert");
        assertEq(_revertSelector(ret), IERCXXXXMandatedVault.AdapterNotAllowed.selector, "unexpected selector");
    }

    function test_bscFork_us04_allowlist_nonZeroActionValue() public {
        MandatedVaultClone vault = _createVault(BSC_BUSD, bytes32("US04_NONZERO_VALUE"));

        CoreNoopAdapter adapterA = new CoreNoopAdapter();
        CoreNoopAdapter adapterB = new CoreNoopAdapter();
        CoreNoopAdapter adapterC = new CoreNoopAdapter();

        // Reuse buildTree3 to construct a three-leaf allowlist.
        (bytes32 root, bytes32[][] memory proofs3) =
            MerkleHelper.buildTree3(_leaf(address(adapterA)), _leaf(address(adapterB)), _leaf(address(adapterC)));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action({
            adapter: address(adapterA), value: 1, data: abi.encodeCall(CoreNoopAdapter.nop, ())
        });

        bytes32[][] memory proofs = new bytes32[][](1);
        proofs[0] = proofs3[0];

        IERCXXXXMandatedVault.Mandate memory m = _mandate(vault, executor, _nextNonce(), root, bytes32(0));
        bytes memory sig = _sign(vault, m, authorityKey);

        (bool ok, bytes memory ret) = _execRaw(vault, m, actions, sig, proofs, executor);

        assertTrue(!ok, "expected revert");
        assertEq(_revertSelector(ret), IERCXXXXMandatedVault.NonZeroActionValue.selector, "unexpected selector");
    }

    function _nextNonce() internal returns (uint256) {
        return nonceCounter++;
    }

    function _createVault(address asset, bytes32 salt) internal returns (MandatedVaultClone v) {
        vm.prank(creator);
        v = MandatedVaultClone(payable(factory.createVault(asset, "BSC Core Vault", "bcVAULT", authority, salt)));
    }

    function _mandate(
        MandatedVaultClone v,
        address mandateExecutor,
        uint256 nonce,
        bytes32 adaptersRoot,
        bytes32 payloadDigest
    ) internal view returns (IERCXXXXMandatedVault.Mandate memory) {
        return IERCXXXXMandatedVault.Mandate({
            executor: mandateExecutor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: adaptersRoot,
            payloadDigest: payloadDigest,
            extensionsHash: keccak256("")
        });
    }

    function _sign(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m, uint256 signerKey)
        internal
        view
        returns (bytes memory)
    {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(signerKey, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    function _leaf(address addr) internal view returns (bytes32) {
        return keccak256(abi.encode(addr, addr.codehash));
    }

    function _singleEmptyProof() internal pure returns (bytes32[][] memory proofs) {
        proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);
    }

    function _execRaw(
        MandatedVaultClone v,
        IERCXXXXMandatedVault.Mandate memory m,
        IERCXXXXMandatedVault.Action[] memory actions,
        bytes memory sig,
        bytes32[][] memory proofs,
        address caller
    ) internal returns (bool ok, bytes memory ret) {
        bytes memory payload = abi.encodeCall(MandatedVaultClone.execute, (m, actions, sig, proofs, bytes("")));
        vm.prank(caller);
        (ok, ret) = address(v).call(payload);
    }

    function _revertSelector(bytes memory revertData) internal pure returns (bytes4 sel) {
        if (revertData.length < 4) return bytes4(0);
        assembly ("memory-safe") {
            sel := mload(add(revertData, 32))
        }
    }

    function _decodeActionCallFailed(bytes memory revertData)
        internal
        pure
        returns (uint256 index, bytes memory reason)
    {
        require(_revertSelector(revertData) == IERCXXXXMandatedVault.ActionCallFailed.selector, "not ActionCallFailed");
        return abi.decode(_slice(revertData, 4), (uint256, bytes));
    }

    function _slice(bytes memory data, uint256 start) internal pure returns (bytes memory out) {
        require(start <= data.length, "slice out of bounds");
        out = new bytes(data.length - start);
        for (uint256 i = 0; i < out.length; ++i) {
            out[i] = data[i + start];
        }
    }
}
