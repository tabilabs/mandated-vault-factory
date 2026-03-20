// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERC8192MandatedVault} from "../src/interfaces/IERC8192MandatedVault.sol";

import {
    BASE_CHAIN_ID,
    BASE_USDC,
    BASE_WETH,
    BASE_USDC_WETH_FEE,
    BASE_AAVE_POOL,
    BASE_UNISWAP_V3_ROUTER,
    BASE_AERODROME_ROUTER,
    BASE_COMPOUND_COMET,
    IAavePoolLike,
    IUniswapRouterLike,
    IAerodromeRouterLike,
    ICometLike
} from "./helpers/BaseForkConstants.sol";
import {VaultForkBaseBase} from "./VaultForkBase.Base.t.sol";

/// @title VaultForkBaseSmokeTest
/// @notice End-to-end Base fork smoke tests against real protocol contracts and live token flows.
contract VaultForkBaseSmokeTest is VaultForkBaseBase {
    function test_baseFork_guard_chainIdAndDeployment() public view {
        assertEq(block.chainid, BASE_CHAIN_ID, "chain id mismatch");
        assertGt(address(factory).code.length, 0, "factory not deployed");
    }

    function test_baseFork_deterministic_usdc_depositWithdraw() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 depositAmt = 1_000e6;

        _depositToVault(v, BASE_USDC, depositAmt);

        assertEq(v.totalAssets(), depositAmt, "totalAssets after deposit");

        vm.prank(bob);
        uint256 burnedShares = v.withdraw(depositAmt / 2, bob, bob);
        assertGt(burnedShares, 0, "withdraw should burn shares");
        assertEq(v.totalAssets(), depositAmt / 2, "totalAssets after withdraw");
    }

    function test_baseFork_smoke_aave_supplyFromDepositedVault() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 amount = 2_000e6;

        _depositToVault(v, BASE_USDC, amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _rootForPair(BASE_USDC, BASE_AAVE_POOL);

        IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
        actions[0] =
            IERC8192MandatedVault.Action(BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_AAVE_POOL, amount)));
        actions[1] = IERC8192MandatedVault.Action(
            BASE_AAVE_POOL, 0, abi.encodeCall(IAavePoolLike.supply, (BASE_USDC, amount, address(v), 0))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = aaveProof;

        IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        _exec(v, m, actions, proofs);

        (uint256 collateral,,,,,) = IAavePoolLike(BASE_AAVE_POOL).getUserAccountData(address(v));
        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault USDC should be fully supplied");
        assertGt(collateral, 0, "Aave collateral should be non-zero");
    }

    function test_baseFork_smoke_aave_withdrawRoundTrip() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 amount = 2_000e6;

        _depositToVault(v, BASE_USDC, amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory aaveProof) = _rootForPair(BASE_USDC, BASE_AAVE_POOL);

        {
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] =
                IERC8192MandatedVault.Action(BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_AAVE_POOL, amount)));
            actions[1] = IERC8192MandatedVault.Action(
                BASE_AAVE_POOL, 0, abi.encodeCall(IAavePoolLike.supply, (BASE_USDC, amount, address(v), 0))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = aaveProof;

            _exec(v, _mandate(v, _nextNonce(), 10000, root), actions, proofs);
        }

        {
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](1);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_AAVE_POOL, 0, abi.encodeCall(IAavePoolLike.withdraw, (BASE_USDC, type(uint256).max, address(v)))
            );

            bytes32[][] memory proofs = new bytes32[][](1);
            proofs[0] = aaveProof;

            _exec(v, _unwindMandate(v, _nextNonce(), root), actions, proofs);
        }

        (uint256 collateral,,,,,) = IAavePoolLike(BASE_AAVE_POOL).getUserAccountData(address(v));
        assertApproxEqAbs(IERC20(BASE_USDC).balanceOf(address(v)), amount, 2, "USDC should return to vault");
        assertEq(collateral, 0, "Aave collateral should be fully withdrawn");
    }

    function test_baseFork_smoke_uniswap_swapExact() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 amount = 1_000e6;

        _depositToVault(v, BASE_USDC, amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory routerProof) =
            _rootForPair(BASE_USDC, BASE_UNISWAP_V3_ROUTER);

        uint256 quotedAmountOut = _quoteUniswapExactInputSingle(BASE_USDC, BASE_WETH, amount, BASE_USDC_WETH_FEE);
        uint256 amountOutMinimum = (quotedAmountOut * 99) / 100;

        IUniswapRouterLike.ExactInputSingleParams memory swapParams = IUniswapRouterLike.ExactInputSingleParams({
            tokenIn: BASE_USDC,
            tokenOut: BASE_WETH,
            fee: BASE_USDC_WETH_FEE,
            recipient: address(v),
            amountIn: amount,
            amountOutMinimum: amountOutMinimum,
            sqrtPriceLimitX96: 0
        });

        IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
        actions[0] = IERC8192MandatedVault.Action(
            BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_UNISWAP_V3_ROUTER, amount))
        );
        actions[1] = IERC8192MandatedVault.Action(
            BASE_UNISWAP_V3_ROUTER, 0, abi.encodeCall(IUniswapRouterLike.exactInputSingle, (swapParams))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = routerProof;

        IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        _exec(v, m, actions, proofs);

        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "USDC should be swapped out");
        assertGe(IERC20(BASE_WETH).balanceOf(address(v)), amountOutMinimum, "WETH output below min");
    }

    function test_baseFork_smoke_compound_supplyFromDepositedVault() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 amount = 2_000e6;

        _depositToVault(v, BASE_USDC, amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory cometProof) =
            _rootForPair(BASE_USDC, BASE_COMPOUND_COMET);

        IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
        actions[0] =
            IERC8192MandatedVault.Action(BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_COMPOUND_COMET, amount)));
        actions[1] = IERC8192MandatedVault.Action(
            BASE_COMPOUND_COMET, 0, abi.encodeCall(ICometLike.supply, (BASE_USDC, amount))
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = cometProof;

        IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        _exec(v, m, actions, proofs);

        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "vault USDC should be fully supplied");
        assertGt(ICometLike(BASE_COMPOUND_COMET).balanceOf(address(v)), 0, "Comet balance should be non-zero");
    }

    function test_baseFork_smoke_compound_withdrawRoundTrip() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 amount = 2_000e6;

        _depositToVault(v, BASE_USDC, amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory cometProof) =
            _rootForPair(BASE_USDC, BASE_COMPOUND_COMET);

        {
            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_COMPOUND_COMET, amount))
            );
            actions[1] = IERC8192MandatedVault.Action(
                BASE_COMPOUND_COMET, 0, abi.encodeCall(ICometLike.supply, (BASE_USDC, amount))
            );

            bytes32[][] memory proofs = new bytes32[][](2);
            proofs[0] = usdcProof;
            proofs[1] = cometProof;

            _exec(v, _mandate(v, _nextNonce(), 10000, root), actions, proofs);
        }

        {
            uint256 cometBal = ICometLike(BASE_COMPOUND_COMET).balanceOf(address(v));

            IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](1);
            actions[0] = IERC8192MandatedVault.Action(
                BASE_COMPOUND_COMET, 0, abi.encodeCall(ICometLike.withdraw, (BASE_USDC, cometBal))
            );

            bytes32[][] memory proofs = new bytes32[][](1);
            proofs[0] = cometProof;

            _exec(v, _unwindMandate(v, _nextNonce(), root), actions, proofs);
        }

        assertApproxEqAbs(IERC20(BASE_USDC).balanceOf(address(v)), amount, 10, "USDC should return to vault");
        assertEq(ICometLike(BASE_COMPOUND_COMET).balanceOf(address(v)), 0, "Comet balance should be fully withdrawn");
    }

    function test_baseFork_smoke_aerodrome_swapExact() public {
        MandatedVaultClone v = _createVault(BASE_USDC);
        uint256 amount = 1_000e6;

        _depositToVault(v, BASE_USDC, amount);

        (bytes32 root, bytes32[] memory usdcProof, bytes32[] memory routerProof) =
            _rootForPair(BASE_USDC, BASE_AERODROME_ROUTER);

        address factory = IAerodromeRouterLike(BASE_AERODROME_ROUTER).defaultFactory();
        IAerodromeRouterLike.Route[] memory routes = new IAerodromeRouterLike.Route[](1);
        routes[0] = IAerodromeRouterLike.Route({from: BASE_USDC, to: BASE_WETH, stable: false, factory: factory});

        uint256[] memory quoted = IAerodromeRouterLike(BASE_AERODROME_ROUTER).getAmountsOut(amount, routes);
        uint256 amountOutMin = (quoted[quoted.length - 1] * 99) / 100;

        IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
        actions[0] =
            IERC8192MandatedVault.Action(BASE_USDC, 0, abi.encodeCall(IERC20.approve, (BASE_AERODROME_ROUTER, amount)));
        actions[1] = IERC8192MandatedVault.Action(
            BASE_AERODROME_ROUTER,
            0,
            abi.encodeCall(
                // Tight deadline is intentional in fork smoke: same-tx execution, no mempool latency model.
                IAerodromeRouterLike.swapExactTokensForTokens,
                (amount, amountOutMin, routes, address(v), block.timestamp + 1)
            )
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = usdcProof;
        proofs[1] = routerProof;

        IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        _exec(v, m, actions, proofs);

        assertEq(IERC20(BASE_USDC).balanceOf(address(v)), 0, "USDC should be swapped out");
        assertGe(IERC20(BASE_WETH).balanceOf(address(v)), amountOutMin, "WETH output below min");
    }
}
