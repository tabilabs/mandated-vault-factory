// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

// --- Fork configuration ---
uint256 constant BASE_CHAIN_ID = 8453;
uint256 constant BASE_FORK_BLOCK = 0;

// --- Tokens ---
address constant BASE_USDC = 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913;
address constant BASE_WETH = 0x4200000000000000000000000000000000000006;
uint24 constant BASE_USDC_WETH_FEE = 500;

// --- Protocol anchors ---
address constant BASE_AAVE_PROVIDER = 0xe20fCBdBfFC4Dd138cE8b2E6FBb6CB49777ad64D;
address constant BASE_AAVE_POOL = 0xA238Dd80C259a72e81d7e4664a9801593F98d1c5;
address constant BASE_MORPHO = 0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb;
address constant BASE_UNISWAP_V3_FACTORY = 0x33128a8fC17869897dcE68Ed026d694621f6FDfD;
address constant BASE_UNISWAP_QUOTER_V2 = 0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a;
address constant BASE_UNISWAP_V3_ROUTER = 0x2626664c2603336E57B271c5C0b26F421741e481;
address constant BASE_AERODROME_ROUTER = 0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43;
address constant BASE_COMPOUND_COMET = 0xb125E6687d4313864e53df431d5425969c15Eb2F;

/// @notice Minimal Aave V3 pool interface used by Base fork tests.
interface IAavePoolLike {
    function ADDRESSES_PROVIDER() external view returns (address);
    function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;
    function withdraw(address asset, uint256 amount, address to) external returns (uint256);
    function getUserAccountData(address user)
        external
        view
        returns (
            uint256 totalCollateralBase,
            uint256 totalDebtBase,
            uint256 availableBorrowsBase,
            uint256 currentLiquidationThreshold,
            uint256 ltv,
            uint256 healthFactor
        );
}

/// @notice Minimal Uniswap `SwapRouter02` interface for Base mainnet smoke tests.
interface IUniswapRouterLike {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function WETH9() external view returns (address);
    function factory() external view returns (address);
    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

/// @notice Minimal Uniswap QuoterV2 interface used to derive non-zero slippage bounds.
interface IQuoterV2Like {
    struct QuoteExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint256 amountIn;
        uint24 fee;
        uint160 sqrtPriceLimitX96;
    }

    function quoteExactInputSingle(QuoteExactInputSingleParams memory params)
        external
        returns (uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate);
}

/// @notice Minimal Uniswap V3 factory interface for Base fork tests.
interface IUniswapV3FactoryLike {
    function getPool(address tokenA, address tokenB, uint24 fee) external view returns (address);
}

/// @notice Minimal Compound V3 Comet interface used by Base fork tests.
interface ICometLike {
    function baseToken() external view returns (address);
    function supply(address asset, uint256 amount) external;
    function withdraw(address asset, uint256 amount) external;
    function balanceOf(address account) external view returns (uint256);
}

/// @notice Minimal Aerodrome router interface used by Base fork tests.
interface IAerodromeRouterLike {
    struct Route {
        address from;
        address to;
        bool stable;
        address factory;
    }

    function weth() external view returns (address);
    function defaultFactory() external view returns (address);
    function poolFor(address tokenA, address tokenB, bool stable, address factory) external view returns (address pool);
    function getAmountsOut(uint256 amountIn, Route[] memory routes) external view returns (uint256[] memory amounts);
    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        Route[] calldata routes,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);
}

/// @notice Minimal Morpho singleton interface used by Base anchor checks.
interface IMorphoLike {
    function owner() external view returns (address);
}
