// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

import {
    BASE_CHAIN_ID,
    BASE_USDC,
    BASE_WETH,
    BASE_USDC_WETH_FEE,
    BASE_AAVE_PROVIDER,
    BASE_AAVE_POOL,
    BASE_MORPHO,
    BASE_UNISWAP_V3_FACTORY,
    BASE_UNISWAP_QUOTER_V2,
    BASE_UNISWAP_V3_ROUTER,
    BASE_AERODROME_ROUTER,
    BASE_COMPOUND_COMET,
    IAavePoolLike,
    IUniswapRouterLike,
    IQuoterV2Like,
    IUniswapV3FactoryLike,
    ICometLike,
    IAerodromeRouterLike,
    IMorphoLike
} from "./helpers/BaseForkConstants.sol";

/// @title VaultForkBaseProtocolAnchorsTest
/// @notice Validates official Base protocol anchor addresses and critical runtime relationships.
contract VaultForkBaseProtocolAnchorsTest is Test {
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

        if (block.chainid != BASE_CHAIN_ID) {
            vm.skip(true, "unexpected chainid: expected Base mainnet fork");
            return;
        }
    }

    function test_baseFork_protocolAnchors_haveRuntimeCode() public view {
        assertGt(BASE_USDC.code.length, 0, "USDC missing code");
        assertGt(BASE_WETH.code.length, 0, "WETH missing code");
        assertGt(BASE_AAVE_POOL.code.length, 0, "Aave pool missing code");
        assertGt(BASE_MORPHO.code.length, 0, "Morpho missing code");
        assertGt(BASE_UNISWAP_QUOTER_V2.code.length, 0, "Uniswap quoter missing code");
        assertGt(BASE_UNISWAP_V3_ROUTER.code.length, 0, "Uniswap router missing code");
        assertGt(BASE_AERODROME_ROUTER.code.length, 0, "Aerodrome router missing code");
        assertGt(BASE_COMPOUND_COMET.code.length, 0, "Compound comet missing code");
    }

    function test_baseFork_protocolAnchors_matchExpectedRelationships() public view {
        assertEq(IAavePoolLike(BASE_AAVE_POOL).ADDRESSES_PROVIDER(), BASE_AAVE_PROVIDER, "Aave provider mismatch");
        assertEq(IUniswapRouterLike(BASE_UNISWAP_V3_ROUTER).WETH9(), BASE_WETH, "Uniswap WETH mismatch");
        assertEq(IUniswapRouterLike(BASE_UNISWAP_V3_ROUTER).factory(), BASE_UNISWAP_V3_FACTORY, "Uniswap factory mismatch");
        assertEq(ICometLike(BASE_COMPOUND_COMET).baseToken(), BASE_USDC, "Compound base token mismatch");
        assertEq(IAerodromeRouterLike(BASE_AERODROME_ROUTER).weth(), BASE_WETH, "Aerodrome WETH mismatch");
        assertGt(IAerodromeRouterLike(BASE_AERODROME_ROUTER).defaultFactory().code.length, 0, "Aerodrome factory missing");
        assertTrue(IMorphoLike(BASE_MORPHO).owner() != address(0), "Morpho owner missing");
    }

    function test_baseFork_protocolAnchors_haveExpectedPools() public view {
        address pool = IUniswapV3FactoryLike(BASE_UNISWAP_V3_FACTORY).getPool(BASE_USDC, BASE_WETH, BASE_USDC_WETH_FEE);
        assertGt(pool.code.length, 0, "Uniswap USDC/WETH pool missing");

        address aerodromeFactory = IAerodromeRouterLike(BASE_AERODROME_ROUTER).defaultFactory();
        address aerodromePool = IAerodromeRouterLike(BASE_AERODROME_ROUTER).poolFor(
            BASE_USDC, BASE_WETH, false, aerodromeFactory
        );
        assertGt(aerodromePool.code.length, 0, "Aerodrome USDC/WETH pool missing");
    }

    function test_baseFork_protocolAnchors_uniswapQuoterReturnsNonZeroQuote() public {
        assertGt(_quoteUniswapExactInputSingle(1e6), 0, "Uniswap quoter returned zero");
    }

    function _quoteUniswapExactInputSingle(uint256 amountIn) internal returns (uint256 amountOut) {
        IQuoterV2Like.QuoteExactInputSingleParams memory params = IQuoterV2Like.QuoteExactInputSingleParams({
            tokenIn: BASE_USDC,
            tokenOut: BASE_WETH,
            amountIn: amountIn,
            fee: BASE_USDC_WETH_FEE,
            sqrtPriceLimitX96: 0
        });

        (amountOut,,,) = IQuoterV2Like(BASE_UNISWAP_QUOTER_V2).quoteExactInputSingle(params);
    }
}
