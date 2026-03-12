// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {IERC8192MandatedVault} from "../src/interfaces/IERC8192MandatedVault.sol";
import {VenusAdapter} from "../src/adapters/VenusAdapter.sol";
import {PancakeSwapV3Adapter} from "../src/adapters/PancakeSwapV3Adapter.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";

import {
    BSC_VENUS_BUSD_UNDERLYING,
    BSC_VENUS_USDT_UNDERLYING,
    BSC_WBNB,
    BSC_VBUSD,
    BSC_VUSDT,
    BSC_BUSD_WBNB_FEE
} from "./helpers/BscForkConstants.sol";
import {VaultForkBscBase} from "./VaultForkBsc.Base.t.sol";

contract VaultForkBscMultiTest is VaultForkBscBase {
    function test_bscFork_smoke_multi_venus_then_pancake() public {
        MandatedVaultClone v = _createVault(BSC_VENUS_BUSD_UNDERLYING);
        uint256 amount = 2_000e18;
        uint256 half = amount / 2;
        deal(BSC_VENUS_BUSD_UNDERLYING, address(v), amount);

        {
            (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
                _rootForPair(BSC_VENUS_BUSD_UNDERLYING, address(venusAdapter));
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                BSC_VENUS_BUSD_UNDERLYING, 0, abi.encodeCall(IERC20.approve, (address(venusAdapter), half))
            );
            actions[1] = IERC8192MandatedVault.Action(
                address(venusAdapter), 0, abi.encodeCall(VenusAdapter.supply, (BSC_VBUSD, half))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = busdProof;
            proofs[1] = adapterProof;

            IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
            (bool ok, bytes memory ret) = _execRaw(v, m, actions, proofs);
            if (!ok) {
                assertEq(_revertSelector(ret), IERC8192MandatedVault.ActionCallFailed.selector, "unexpected selector");
                (uint256 idx, bytes memory reason) = _decodeActionCallFailed(ret);
                assertEq(idx, 1, "unexpected failing action");
                if (_isVenusProtocolUnavailable(reason)) {
                    vm.skip(
                        true,
                        _unavailableMessage(
                            "venus supply unavailable on current fork head",
                            BSC_VENUS_BUSD_UNDERLYING,
                            BSC_VBUSD,
                            reason
                        )
                    );
                    return;
                }
                revert(
                    _unavailableMessage(
                        "venus supply failed (not protocol issue)", BSC_VENUS_BUSD_UNDERLYING, BSC_VBUSD, reason
                    )
                );
            }
        }

        {
            (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
                _rootForPair(BSC_VENUS_BUSD_UNDERLYING, address(pancakeAdapter));
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                BSC_VENUS_BUSD_UNDERLYING, 0, abi.encodeCall(IERC20.approve, (address(pancakeAdapter), half))
            );
            actions[1] = IERC8192MandatedVault.Action(
                address(pancakeAdapter),
                0,
                abi.encodeCall(
                    PancakeSwapV3Adapter.swap,
                    (BSC_VENUS_BUSD_UNDERLYING, BSC_WBNB, BSC_BUSD_WBNB_FEE, block.timestamp + 300, half, 1)
                )
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = busdProof;
            proofs[1] = adapterProof;

            IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
            (bool ok, bytes memory ret) = _execRaw(v, m, actions, proofs);
            if (!ok) {
                assertEq(_revertSelector(ret), IERC8192MandatedVault.ActionCallFailed.selector, "unexpected selector");
                (uint256 idx, bytes memory reason) = _decodeActionCallFailed(ret);
                assertEq(idx, 1, "unexpected failing action");
                if (_isPancakeProtocolUnavailable(reason)) {
                    vm.skip(
                        true,
                        _unavailableMessage(
                            "pancake swap unavailable on current fork head", BSC_VENUS_BUSD_UNDERLYING, BSC_WBNB, reason
                        )
                    );
                    return;
                }
                revert(
                    _unavailableMessage(
                        "pancake swap failed (not protocol issue)", BSC_VENUS_BUSD_UNDERLYING, BSC_WBNB, reason
                    )
                );
            }
        }

        assertEq(IERC20(BSC_VENUS_BUSD_UNDERLYING).balanceOf(address(v)), 0, "all BUSD should be deployed");
        assertGt(IERC20(BSC_VBUSD).balanceOf(address(v)), 0, "vBUSD leg should exist");
        assertGt(IERC20(BSC_WBNB).balanceOf(address(v)), 0, "WBNB leg should exist");
    }

    function test_bscFork_smoke_fullLifecycle_deposit_execute_unwind_redeem() public {
        uint256 depositAmt = 2_000e18;
        (bool ok, MandatedVaultClone v, address underlying, address vToken, uint256 shares, bytes memory reason) =
            _supplyFromDepositedVaultAnyMarket(depositAmt);

        if (!ok) {
            if (_isVenusProtocolUnavailable(reason)) {
                vm.skip(
                    true,
                    _unavailableMessage("venus lifecycle unavailable on current fork head", underlying, vToken, reason)
                );
                return;
            }
            revert(_unavailableMessage("venus lifecycle failed (not protocol issue)", underlying, vToken, reason));
        }

        uint256 vTokenBal = IERC20(vToken).balanceOf(address(v));
        assertGt(vTokenBal, 0, "vToken received after supply");

        {
            (bytes32 root, bytes32[] memory vTokenProof, bytes32[] memory adapterProof) =
                _rootForPair(vToken, address(venusAdapter));
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                vToken, 0, abi.encodeCall(IERC20.approve, (address(venusAdapter), vTokenBal))
            );
            actions[1] = IERC8192MandatedVault.Action(
                address(venusAdapter), 0, abi.encodeCall(VenusAdapter.withdraw, (vToken, vTokenBal))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = vTokenProof;
            proofs[1] = adapterProof;

            IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
            (bool execOk, bytes memory ret) = _execRaw(v, m, actions, proofs);
            if (!execOk) {
                assertEq(_revertSelector(ret), IERC8192MandatedVault.ActionCallFailed.selector, "unexpected selector");
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

        vm.prank(bob);
        uint256 redeemed = v.redeem(shares, bob, bob);

        assertGt(redeemed, 0, "redeemed should be positive");
        assertGe(redeemed, depositAmt - 1e15, "redeemed too low");
        assertGe(IERC20(underlying).balanceOf(bob), depositAmt - 1e15, "bob final balance too low");
    }

    function _supplyFromDepositedVaultAnyMarket(uint256 depositAmt)
        internal
        returns (bool ok, MandatedVaultClone v, address underlying, address vToken, uint256 shares, bytes memory reason)
    {
        address[2] memory underlyings = [BSC_VENUS_BUSD_UNDERLYING, BSC_VENUS_USDT_UNDERLYING];
        address[2] memory vTokens = [BSC_VBUSD, BSC_VUSDT];

        for (uint256 i = 0; i < underlyings.length; ++i) {
            underlying = underlyings[i];
            vToken = vTokens[i];
            MandatedVaultClone candidateVault = _createVault(underlyings[i]);

            deal(underlyings[i], bob, depositAmt);
            vm.startPrank(bob);
            IERC20(underlyings[i]).approve(address(candidateVault), depositAmt);
            uint256 candidateShares = candidateVault.deposit(depositAmt, bob);
            vm.stopPrank();

            (bytes32 root, bytes32[] memory underlyingProof, bytes32[] memory adapterProof) =
                _rootForPair(underlyings[i], address(venusAdapter));

            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                underlyings[i], 0, abi.encodeCall(IERC20.approve, (address(venusAdapter), depositAmt))
            );
            actions[1] = IERC8192MandatedVault.Action(
                address(venusAdapter), 0, abi.encodeCall(VenusAdapter.supply, (vTokens[i], depositAmt))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = underlyingProof;
            proofs[1] = adapterProof;

            IERC8192MandatedVault.Mandate memory m = _mandate(candidateVault, _nextNonce(), 10000, root);
            (bool execOk, bytes memory ret) = _execRaw(candidateVault, m, actions, proofs);

            if (execOk) {
                return (true, candidateVault, underlyings[i], vTokens[i], candidateShares, bytes(""));
            }

            assertEq(_revertSelector(ret), IERC8192MandatedVault.ActionCallFailed.selector, "unexpected selector");
            (uint256 idx, bytes memory innerReason) = _decodeActionCallFailed(ret);
            assertEq(idx, 1, "unexpected failing action");
            emit log_named_address("lifecycle supply failed underlying", underlyings[i]);
            emit log_named_address("lifecycle supply failed market", vTokens[i]);
            emit log_string(_decodeErrorString(innerReason));
            reason = innerReason;
        }

        return (false, MandatedVaultClone(payable(address(0))), underlying, vToken, 0, reason);
    }
}
