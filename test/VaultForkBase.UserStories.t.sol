// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERC8192MandatedVault} from "../src/interfaces/IERC8192MandatedVault.sol";

import {
    BASE_USDC,
    BASE_WETH,
    BASE_USDC_WETH_FEE,
    BASE_AAVE_POOL,
    BASE_UNISWAP_V3_ROUTER,
    BASE_COMPOUND_COMET,
    IAavePoolLike,
    IUniswapRouterLike,
    ICometLike
} from "./helpers/BaseForkConstants.sol";
import {VaultForkBaseBase} from "./VaultForkBase.Base.t.sol";

/// @title VaultForkBaseUserStoriesTest
/// @notice Base mainnet fork user-journey tests that model real deposit -> strategy -> unwind -> redeem flows.
contract VaultForkBaseUserStoriesTest is VaultForkBaseBase {
    function test_baseFork_userStory_aave_lifecycle_deposit_supply_withdraw_redeem() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 depositAmt = 2_000e6;

        deal(BASE_USDC, bob, depositAmt);
        vm.startPrank(bob);
        IERC20(BASE_USDC).approve(address(v), depositAmt);
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();

        assertEq(shares, depositAmt, "first deposit should mint 1:1 shares");
        assertEq(v.balanceOf(bob), shares, "bob shares after deposit");

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _rootForPair(BASE_USDC, BASE_AAVE_POOL);

        {
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_AAVE_POOL, depositAmt))
            );
            actions[1] = IERC8192MandatedVault.Action(
                BASE_AAVE_POOL, 0, abi.encodeCall(IAavePoolLike.supply, (BASE_USDC, depositAmt, address(v), 0))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = aaveProof;

            _exec(v, _mandate(v, _nextNonce(), 10000, root), actions, proofs);
        }

        (uint256 collateral,,,,,) = IAavePoolLike(BASE_AAVE_POOL).getUserAccountData(address(v));
        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault USDC should be deployed into Aave");
        assertGt(collateral, 0, "Aave collateral should exist after supply");

        {
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](1);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_AAVE_POOL, 0, abi.encodeCall(IAavePoolLike.withdraw, (BASE_USDC, type(uint256).max, address(v)))
            );

            bytes32[][] memory proofs = new bytes32[][](1);
            proofs[0] = aaveProof;

            _exec(v, _unwindMandate(v, _nextNonce(), root), actions, proofs);
        }

        (collateral,,,,,) = IAavePoolLike(BASE_AAVE_POOL).getUserAccountData(address(v));
        assertEq(collateral, 0, "Aave collateral should be fully unwound");
        assertApproxEqAbs(IERC20(BASE_USDC).balanceOf(address(v)), depositAmt, 2, "USDC should return to vault");

        uint256 redeemed = _redeemAllShares(v);

        assertApproxEqAbs(redeemed, depositAmt, 2, "redeem output mismatch");
        assertApproxEqAbs(IERC20(BASE_USDC).balanceOf(bob), depositAmt, 2, "bob final USDC mismatch");
        assertEq(v.balanceOf(bob), 0, "bob shares should be burned");
        assertEq(v.totalSupply(), 0, "vault totalSupply should be zero after full redeem");
        assertEq(v.totalAssets(), 0, "vault totalAssets should be zero after full redeem");
        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault should not retain USDC after redeem");
    }

    function test_baseFork_userStory_compound_lifecycle_deposit_supply_withdraw_redeem() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 depositAmt = 2_000e6;

        deal(BASE_USDC, bob, depositAmt);
        vm.startPrank(bob);
        IERC20(BASE_USDC).approve(address(v), depositAmt);
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();

        assertEq(shares, depositAmt, "first deposit should mint 1:1 shares");
        assertEq(v.balanceOf(bob), shares, "bob shares after deposit");

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory cometProof) =
            _rootForPair(BASE_USDC, BASE_COMPOUND_COMET);

        {
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_COMPOUND_COMET, depositAmt))
            );
            actions[1] = IERC8192MandatedVault.Action(
                BASE_COMPOUND_COMET, 0, abi.encodeCall(ICometLike.supply, (BASE_USDC, depositAmt))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = cometProof;

            _exec(v, _mandate(v, _nextNonce(), 10000, root), actions, proofs);
        }

        uint256 cometBal = ICometLike(BASE_COMPOUND_COMET).balanceOf(address(v));
        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault USDC should be deployed into Compound");
        assertGt(cometBal, 0, "Comet position should exist after supply");

        {
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](1);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_COMPOUND_COMET, 0, abi.encodeCall(ICometLike.withdraw, (BASE_USDC, cometBal))
            );

            bytes32[][] memory proofs = new bytes32[][](1);
            proofs[0] = cometProof;

            _exec(v, _unwindMandate(v, _nextNonce(), root), actions, proofs);
        }

        assertEq(ICometLike(BASE_COMPOUND_COMET).balanceOf(address(v)), 0, "Comet position should be fully unwound");
        assertApproxEqAbs(IERC20(BASE_USDC).balanceOf(address(v)), depositAmt, 10, "USDC should return to vault");

        uint256 redeemed = _redeemAllShares(v);

        assertApproxEqAbs(redeemed, depositAmt, 10, "redeem output mismatch");
        assertApproxEqAbs(IERC20(BASE_USDC).balanceOf(bob), depositAmt, 10, "bob final USDC mismatch");
        assertEq(v.balanceOf(bob), 0, "bob shares should be burned");
        assertEq(v.totalSupply(), 0, "vault totalSupply should be zero after full redeem");
        assertEq(v.totalAssets(), 0, "vault totalAssets should be zero after full redeem");
        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault should not retain USDC after redeem");
    }

    function test_baseFork_userStory_uniswap_lifecycle_deposit_roundTrip_redeem() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 depositAmt = 1_000e6;

        deal(BASE_USDC, bob, depositAmt);
        vm.startPrank(bob);
        IERC20(BASE_USDC).approve(address(v), depositAmt);
        uint256 shares = v.deposit(depositAmt, bob);
        vm.stopPrank();

        assertEq(shares, depositAmt, "first deposit should mint 1:1 shares");
        assertEq(v.balanceOf(bob), shares, "bob shares after deposit");

        {
            (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory routerProof) =
                _rootForPair(BASE_USDC, BASE_UNISWAP_V3_ROUTER);

            uint256 quotedWethOut = _quoteUniswapExactInputSingle(BASE_USDC, BASE_WETH, depositAmt, BASE_USDC_WETH_FEE);
            uint256 amountOutMinimum = (quotedWethOut * 99) / 100;

            IUniswapRouterLike.ExactInputSingleParams memory swapParams = IUniswapRouterLike.ExactInputSingleParams({
                tokenIn: BASE_USDC,
                tokenOut: BASE_WETH,
                fee: BASE_USDC_WETH_FEE,
                recipient: address(v),
                amountIn: depositAmt,
                amountOutMinimum: amountOutMinimum,
                sqrtPriceLimitX96: 0
            });

            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_UNISWAP_V3_ROUTER, depositAmt))
            );
            actions[1] = IERC8192MandatedVault.Action(
                BASE_UNISWAP_V3_ROUTER, 0, abi.encodeCall(IUniswapRouterLike.exactInputSingle, (swapParams))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = routerProof;

            _exec(v, _mandate(v, _nextNonce(), 10000, root), actions, proofs);

            assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault USDC should be swapped out");
            assertGe(IERC20(BASE_WETH).balanceOf(address(v)), amountOutMinimum, "WETH output below min");
        }

        uint256 wethBalance = IERC20(BASE_WETH).balanceOf(address(v));
        uint256 quotedUsdcOut = _quoteUniswapExactInputSingle(BASE_WETH, BASE_USDC, wethBalance, BASE_USDC_WETH_FEE);
        uint256 amountOutMinimumBack = (quotedUsdcOut * 99) / 100;

        {
            (bytes32 root, bytes32[] memory wethProof, bytes32[] memory routerProof) =
                _rootForPair(BASE_WETH, BASE_UNISWAP_V3_ROUTER);

            IUniswapRouterLike.ExactInputSingleParams memory swapParams = IUniswapRouterLike.ExactInputSingleParams({
                tokenIn: BASE_WETH,
                tokenOut: BASE_USDC,
                fee: BASE_USDC_WETH_FEE,
                recipient: address(v),
                amountIn: wethBalance,
                amountOutMinimum: amountOutMinimumBack,
                sqrtPriceLimitX96: 0
            });

            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_WETH, 0, abi.encodeCall(IERC20.approve, (BASE_UNISWAP_V3_ROUTER, wethBalance))
            );
            actions[1] = IERC8192MandatedVault.Action(
                BASE_UNISWAP_V3_ROUTER, 0, abi.encodeCall(IUniswapRouterLike.exactInputSingle, (swapParams))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = wethProof;
            proofs[1] = routerProof;

            _exec(v, _unwindMandate(v, _nextNonce(), root), actions, proofs);
        }

        uint256 vaultRecoveredUsdc = IERC20(BASE_USDC).balanceOf(address(v));
        assertEq(IERC20(BASE_WETH).balanceOf(address(v)), 0, "vault WETH should be fully swapped back");
        assertGe(vaultRecoveredUsdc, amountOutMinimumBack, "recovered USDC below slippage guard");
        assertLe(vaultRecoveredUsdc, depositAmt, "round-trip should not exceed initial USDC on same block");

        uint256 redeemed = _redeemAllShares(v);

        assertEq(redeemed, vaultRecoveredUsdc, "redeem should return recovered USDC");
        assertGe(IERC20(BASE_USDC).balanceOf(bob), amountOutMinimumBack, "bob final USDC below slippage guard");
        assertLe(IERC20(BASE_USDC).balanceOf(bob), depositAmt, "bob should not receive more than initial USDC");
        assertEq(v.balanceOf(bob), 0, "bob shares should be burned");
        assertEq(v.totalSupply(), 0, "vault totalSupply should be zero after full redeem");
        assertEq(v.totalAssets(), 0, "vault totalAssets should be zero after full redeem");
        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault should not retain USDC after redeem");
    }
}
