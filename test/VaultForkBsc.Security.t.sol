// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";

import {BSC_CHAIN_ID, BSC_BUSD} from "./helpers/BscForkConstants.sol";
import {MerkleHelper} from "./helpers/MerkleHelper.sol";

contract SecurityNoopAdapter {
    function nop() external {}
}

contract SecurityBurnAssetAdapter {
    using SafeERC20 for IERC20;

    function pullFromCaller(address token, address to, uint256 amount) external {
        IERC20(token).safeTransferFrom(msg.sender, to, amount);
    }
}

contract VaultForkBscSecurityTest is Test {
    VaultFactory internal factory;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);

    uint256 internal nonceCounter;

    SecurityNoopAdapter internal noopAdapter;
    SecurityBurnAssetAdapter internal burnAdapter;

    function setUp() public {
        // These tests are intentionally deterministic and MUST NOT depend on external protocol
        // availability (e.g., Venus / Pancake). We only require a BSC testnet fork backend.

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

        // Optional: allow pinning a specific block for reproduction.
        if (vm.envExists("BSC_FORK_BLOCK")) {
            uint256 forkBlock = vm.envUint("BSC_FORK_BLOCK");
            if (block.number != forkBlock) {
                try vm.rollFork(forkBlock) {} catch {
                    vm.skip(true, "failed to roll fork to BSC_FORK_BLOCK");
                    return;
                }
            }
        }

        assertGt(BSC_BUSD.code.length, 0, "BUSD missing code");

        authority = vm.addr(authorityKey);
        factory = new VaultFactory();

        noopAdapter = new SecurityNoopAdapter();
        burnAdapter = new SecurityBurnAssetAdapter();
    }

    function test_bscFork_us08_drawdownBreaker_revertDrawdownExceeded_postExecutionDirect() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 initialAssets = 1_000e18;
        uint256 drainAmount = 60e18; // 6% > 5%
        deal(BSC_BUSD, address(v), initialAssets);

        (bytes32 root, bytes32[] memory tokenProof, bytes32[] memory adapterProof) = _rootForPair(BSC_BUSD, address(burnAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(
            BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(burnAdapter), drainAmount))
        );
        actions[1] = IERCXXXXMandatedVault.Action(
            address(burnAdapter),
            0,
            abi.encodeCall(SecurityBurnAssetAdapter.pullFromCaller, (BSC_BUSD, address(0xDEAD), drainAmount))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = tokenProof;
        proofs[1] = adapterProof;

        IERCXXXXMandatedVault.Mandate memory m = _buildMandate(v, _nextNonce(), root, 500, 1000);
        (bool ok, bytes memory ret) = _execRaw(v, m, actions, proofs);

        assertTrue(!ok, "expected revert");
        bytes4 sel = _revertSelector(ret);
        assertTrue(sel != IERCXXXXMandatedVault.ActionCallFailed.selector, "unexpected ActionCallFailed");
        assertEq(sel, IERCXXXXMandatedVault.DrawdownExceeded.selector, "unexpected revert selector");
    }

    function test_bscFork_us08_drawdownBreaker_revertCumulativeDrawdownExceeded_postExecutionDirect() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 initialAssets = 1_000e18;
        deal(BSC_BUSD, address(v), initialAssets);

        (bytes32 root, bytes32[] memory tokenProof, bytes32[] memory adapterProof) = _rootForPair(BSC_BUSD, address(burnAdapter));

        // first: 4% loss, should pass
        {
            IERCXXXXMandatedVault.Action[] memory actions1 = new IERCXXXXMandatedVault.Action[](2);
            actions1[0] = IERCXXXXMandatedVault.Action(
                BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(burnAdapter), 40e18))
            );
            actions1[1] = IERCXXXXMandatedVault.Action(
                address(burnAdapter),
                0,
                abi.encodeCall(SecurityBurnAssetAdapter.pullFromCaller, (BSC_BUSD, address(0xDEAD), 40e18))
            );

            bytes32[][] memory proofs1 = new bytes32[][](2);
            proofs1[0] = tokenProof;
            proofs1[1] = adapterProof;

            IERCXXXXMandatedVault.Mandate memory m1 = _buildMandate(v, _nextNonce(), root, 800, 1000);
            (uint256 pre1, uint256 post1) = _exec(v, m1, actions1, proofs1);
            assertEq(pre1, 1_000e18, "unexpected preAssets");
            assertEq(post1, 960e18, "unexpected postAssets");
        }

        // second: single loss 70/960 = 7.29% (<8%), cumulative loss 110/1000 = 11% (>10%)
        {
            IERCXXXXMandatedVault.Action[] memory actions2 = new IERCXXXXMandatedVault.Action[](2);
            actions2[0] = IERCXXXXMandatedVault.Action(
                BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(burnAdapter), 70e18))
            );
            actions2[1] = IERCXXXXMandatedVault.Action(
                address(burnAdapter),
                0,
                abi.encodeCall(SecurityBurnAssetAdapter.pullFromCaller, (BSC_BUSD, address(0xDEAD), 70e18))
            );

            bytes32[][] memory proofs2 = new bytes32[][](2);
            proofs2[0] = tokenProof;
            proofs2[1] = adapterProof;

            IERCXXXXMandatedVault.Mandate memory m2 = _buildMandate(v, _nextNonce(), root, 800, 1000);
            (bool ok, bytes memory ret) = _execRaw(v, m2, actions2, proofs2);

            assertTrue(!ok, "expected revert");
            bytes4 sel = _revertSelector(ret);
            assertTrue(sel != IERCXXXXMandatedVault.ActionCallFailed.selector, "unexpected ActionCallFailed");
            assertEq(sel, IERCXXXXMandatedVault.CumulativeDrawdownExceeded.selector, "unexpected revert selector");
        }
    }

    function test_bscFork_us09_nonceThresholdAndRevoke_revertNonceAlreadyUsed() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);

        bytes32 root = _leaf(address(noopAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(SecurityNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        uint256 nonce = _nextNonce();
        IERCXXXXMandatedVault.Mandate memory m = _buildMandate(v, nonce, root, 500, 1000);
        _exec(v, m, actions, proofs);

        bytes memory sig = _sign(v, m);
        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.NonceAlreadyUsed.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    function test_bscFork_us09_nonceThresholdAndRevoke_revertNonceBelowThreshold_afterInvalidateBelow() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);

        vm.prank(authority);
        v.invalidateNoncesBelow(10);

        bytes32 root = _leaf(address(noopAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(SecurityNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        IERCXXXXMandatedVault.Mandate memory m = _buildMandate(v, 9, root, 500, 1000);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.NonceBelowThreshold.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    function test_bscFork_us09_nonceThresholdAndRevoke_revertMandateIsRevoked_afterRevokeMandate() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);

        bytes32 root = _leaf(address(noopAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(SecurityNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        IERCXXXXMandatedVault.Mandate memory m = _buildMandate(v, _nextNonce(), root, 500, 1000);
        bytes32 mandateHash = v.hashMandate(m);

        vm.prank(authority);
        v.revokeMandate(mandateHash);

        bytes memory sig = _sign(v, m);
        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.MandateIsRevoked.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    function test_bscFork_us10_authorityTransfer_revertAuthorityEpochMismatch_onOldMandate() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);

        bytes32 root = _leaf(address(noopAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(noopAdapter), 0, abi.encodeCall(SecurityNoopAdapter.nop, ()));

        bytes32[][] memory proofs = _singleEmptyProof();

        IERCXXXXMandatedVault.Mandate memory oldMandate = _buildMandate(v, _nextNonce(), root, 500, 1000);
        bytes memory oldSig = _sign(v, oldMandate);

        address newAuthority = address(0xBEEF);
        vm.prank(authority);
        v.proposeAuthority(newAuthority);

        vm.prank(newAuthority);
        v.acceptAuthority();

        assertEq(v.authorityEpoch(), oldMandate.authorityEpoch + 1, "authority epoch should increment");

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.AuthorityEpochMismatch.selector);
        v.execute(oldMandate, actions, oldSig, proofs, "");
    }

    function _nextNonce() internal returns (uint256) {
        return nonceCounter++;
    }

    function _createVault(address asset) internal returns (MandatedVaultClone v) {
        vm.prank(creator);
        v = MandatedVaultClone(
            payable(factory.createVault(asset, "BSC Security Vault", "bsVAULT", authority, bytes32(nonceCounter)))
        );
    }

    function _sign(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m) internal view returns (bytes memory) {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(authorityKey, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    function _leaf(address addr) internal view returns (bytes32) {
        return keccak256(abi.encode(addr, addr.codehash));
    }

    function _rootForPair(address first, address second)
        internal
        view
        returns (bytes32 root, bytes32[] memory firstProof, bytes32[] memory secondProof)
    {
        return MerkleHelper.buildTree2(_leaf(first), _leaf(second));
    }

    function _buildMandate(MandatedVaultClone v, uint256 nonce, bytes32 root, uint16 maxSingleBps, uint16 maxCumulativeBps)
        internal
        view
        returns (IERCXXXXMandatedVault.Mandate memory)
    {
        return IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: maxSingleBps,
            maxCumulativeDrawdownBps: maxCumulativeBps,
            allowedAdaptersRoot: root,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
    }

    function _exec(
        MandatedVaultClone v,
        IERCXXXXMandatedVault.Mandate memory m,
        IERCXXXXMandatedVault.Action[] memory actions,
        bytes32[][] memory proofs
    ) internal returns (uint256 pre, uint256 post) {
        bytes memory sig = _sign(v, m);
        vm.prank(executor);
        return v.execute(m, actions, sig, proofs, "");
    }

    function _execRaw(
        MandatedVaultClone v,
        IERCXXXXMandatedVault.Mandate memory m,
        IERCXXXXMandatedVault.Action[] memory actions,
        bytes32[][] memory proofs
    ) internal returns (bool ok, bytes memory ret) {
        bytes memory sig = _sign(v, m);
        bytes memory payload = abi.encodeCall(MandatedVaultClone.execute, (m, actions, sig, proofs, bytes("")));
        vm.prank(executor);
        (ok, ret) = address(v).call(payload);
    }

    function _revertSelector(bytes memory revertData) internal pure returns (bytes4 sel) {
        if (revertData.length < 4) return bytes4(0);
        assembly ("memory-safe") {
            sel := mload(add(revertData, 32))
        }
    }

    function _singleEmptyProof() internal pure returns (bytes32[][] memory proofs) {
        proofs = new bytes32[][](1);
        proofs[0] = new bytes32[](0);
    }
}
