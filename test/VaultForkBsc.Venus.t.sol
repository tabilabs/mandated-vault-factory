// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";
import {VenusAdapter} from "../src/adapters/VenusAdapter.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";

import {
    BSC_CHAIN_ID,
    BSC_BUSD,
    BSC_VENUS_BUSD_UNDERLYING,
    BSC_VENUS_USDT_UNDERLYING,
    BSC_VBUSD,
    BSC_VUSDT
} from "./helpers/BscForkConstants.sol";
import {VaultForkBscBase} from "./VaultForkBsc.Base.t.sol";

contract VaultForkBscVenusTest is VaultForkBscBase {
    function test_bscFork_deterministic_guard_chainIdAndDeployment() public view {
        assertEq(block.chainid, BSC_CHAIN_ID, "chain id mismatch");
        assertGt(address(factory).code.length, 0, "factory not deployed");
        assertGt(address(venusAdapter).code.length, 0, "venus adapter not deployed");
    }

    function test_bscFork_deterministic_busd_depositWithdraw() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 depositAmt = 1_000e18;

        deal(BSC_BUSD, bob, depositAmt);

        vm.startPrank(bob);
        IERC20(BSC_BUSD).approve(address(v), depositAmt);
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();

        assertGt(shares, 0, "shares should be > 0");
        assertEq(v.totalAssets(), depositAmt, "totalAssets after deposit");

        vm.prank(bob);
        uint256 withdrawn = v.withdraw(depositAmt / 2, bob, bob);
        assertEq(withdrawn, shares / 2, "withdrawn shares");
        assertEq(v.totalAssets(), depositAmt / 2, "totalAssets after withdraw");
    }

    function test_bscFork_smoke_venus_supply_viaAdapter() public {
        uint256 amount = 2_000e18;
        (bool ok, MandatedVaultClone v, address underlying, address vToken, bytes memory reason) = _trySupplyAny(amount);

        if (!ok) {
            if (_isVenusProtocolUnavailable(reason)) {
                vm.skip(
                    true,
                    _unavailableMessage("venus supply unavailable on current fork head", underlying, vToken, reason)
                );
                return;
            }
            revert(_unavailableMessage("venus supply failed (not protocol issue)", underlying, vToken, reason));
        }

        assertEq(IERC20(underlying).balanceOf(address(v)), 0, "all underlying supplied");
        assertGt(IERC20(vToken).balanceOf(address(v)), 0, "vToken should be received");
    }

    function test_bscFork_smoke_venus_withdraw_viaAdapter() public {
        uint256 amount = 2_000e18;
        (bool ok, MandatedVaultClone v, address underlying, address vToken, bytes memory reason) = _trySupplyAny(amount);

        if (!ok) {
            if (_isVenusProtocolUnavailable(reason)) {
                vm.skip(
                    true,
                    _unavailableMessage("venus supply unavailable on current fork head", underlying, vToken, reason)
                );
                return;
            }
            revert(_unavailableMessage("venus supply failed (not protocol issue)", underlying, vToken, reason));
        }

        uint256 vTokenBal = IERC20(vToken).balanceOf(address(v));
        assertGt(vTokenBal, 0, "vToken precondition");

        {
            (bytes32 root, bytes32[] memory vTokenProof, bytes32[] memory adapterProof) =
                _rootForPair(vToken, address(venusAdapter));
            IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
            actions[0] = IERCXXXXMandatedVault.Action(
                vToken, 0, abi.encodeCall(IERC20.approve, (address(venusAdapter), vTokenBal))
            );
            actions[1] = IERCXXXXMandatedVault.Action(
                address(venusAdapter), 0, abi.encodeCall(VenusAdapter.withdraw, (vToken, vTokenBal))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = vTokenProof;
            proofs[1] = adapterProof;

            IERCXXXXMandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
            (bool execOk, bytes memory ret) = _execRaw(v, m, actions, proofs);
            if (!execOk) {
                assertEq(_revertSelector(ret), IERCXXXXMandatedVault.ActionCallFailed.selector, "unexpected selector");
                (uint256 idx, bytes memory innerReason) = _decodeActionCallFailed(ret);
                assertEq(idx, 1, "unexpected failing action");
                if (_isVenusProtocolUnavailable(innerReason)) {
                    vm.skip(
                        true,
                        _unavailableMessage(
                            "venus withdraw unavailable on current fork head", underlying, vToken, innerReason
                        )
                    );
                    return;
                }
                revert(
                    _unavailableMessage("venus withdraw failed (not protocol issue)", underlying, vToken, innerReason)
                );
            }
        }

        assertGt(IERC20(underlying).balanceOf(address(v)), 0, "underlying should return");
        assertEq(IERC20(vToken).balanceOf(address(v)), 0, "all vToken redeemed");
    }

    function test_bscFork_deterministic_merkleAdapterAllowlist_rejectsUnknownAdapter() public {
        MandatedVaultClone v = _createVault(BSC_VENUS_BUSD_UNDERLYING);
        uint256 amount = 1_000e18;
        deal(BSC_VENUS_BUSD_UNDERLYING, address(v), amount);

        bytes32 root = _leaf(BSC_VENUS_BUSD_UNDERLYING);

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(
            BSC_VENUS_BUSD_UNDERLYING, 0, abi.encodeCall(IERC20.approve, (address(venusAdapter), amount))
        );
        actions[1] = IERCXXXXMandatedVault.Action(
            address(venusAdapter), 0, abi.encodeCall(VenusAdapter.supply, (BSC_VBUSD, amount))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = new bytes32[](0);
        proofs[1] = new bytes32[](0);

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectRevert(IERCXXXXMandatedVault.AdapterNotAllowed.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    function _trySupplyAny(uint256 amount)
        internal
        returns (bool ok, MandatedVaultClone v, address underlying, address vToken, bytes memory reason)
    {
        address[2] memory underlyings = [BSC_VENUS_BUSD_UNDERLYING, BSC_VENUS_USDT_UNDERLYING];
        address[2] memory vTokens = [BSC_VBUSD, BSC_VUSDT];

        for (uint256 i = 0; i < underlyings.length; ++i) {
            underlying = underlyings[i];
            vToken = vTokens[i];
            MandatedVaultClone candidateVault = _createVault(underlyings[i]);
            deal(underlyings[i], address(candidateVault), amount);

            (bytes32 root, bytes32[] memory underlyingProof, bytes32[] memory adapterProof) =
                _rootForPair(underlyings[i], address(venusAdapter));

            IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
            actions[0] = IERCXXXXMandatedVault.Action(
                underlyings[i], 0, abi.encodeCall(IERC20.approve, (address(venusAdapter), amount))
            );
            actions[1] = IERCXXXXMandatedVault.Action(
                address(venusAdapter), 0, abi.encodeCall(VenusAdapter.supply, (vTokens[i], amount))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = underlyingProof;
            proofs[1] = adapterProof;

            IERCXXXXMandatedVault.Mandate memory m = _mandate(candidateVault, _nextNonce(), 10000, root);
            (bool execOk, bytes memory ret) = _execRaw(candidateVault, m, actions, proofs);

            if (execOk) {
                return (true, candidateVault, underlyings[i], vTokens[i], bytes(""));
            }

            assertEq(_revertSelector(ret), IERCXXXXMandatedVault.ActionCallFailed.selector, "unexpected selector");
            (uint256 idx, bytes memory innerReason) = _decodeActionCallFailed(ret);
            assertEq(idx, 1, "unexpected failing action");
            emit log_named_address("venus supply failed underlying", underlyings[i]);
            emit log_named_address("venus supply failed market", vTokens[i]);
            emit log_string(_decodeErrorString(innerReason));
            reason = innerReason;
        }

        return (false, MandatedVaultClone(payable(address(0))), underlying, vToken, reason);
    }
}
