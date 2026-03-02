// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

// ─── Mainnet fork constants & protocol interfaces ────────────────────────────
// Block pinned to ~Nov 2024; all protocols active with sufficient liquidity.

// --- Block ---
uint256 constant FORK_BLOCK = 21_000_000;

// --- Tokens ---
address constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48; // 6 decimals, proxy
address constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2; // 18 decimals
address constant DAI = 0x6B175474E89094C44Da98b954EedeAC495271d0F; // 18 decimals
address constant USDT = 0xdAC17F958D2ee523a2206206994597C13D831ec7; // 6 decimals, non-standard

// --- Aave V3 ---
address constant AAVE_POOL = 0x87870Bca3F3fD6335C3F4ce8392D69350B4fA4E2; // Aave V3 Pool proxy
address constant A_ETH_USDC = 0x98C23E9d8f34FEFb1B7BD6a91B7FF122F4e16F5c; // aEthUSDC (Aave V3 USDC aToken)

// --- Uniswap V3 ---
address constant UNISWAP_ROUTER = 0xE592427A0AEce92De3Edee1F18E0157C05861564;
uint24 constant USDC_WETH_FEE = 500; // 0.05% pool

// --- Compound V3 ---
address constant COMPOUND_COMET = 0xc3d688B66703497DAA19211EEdff47f25384cdc3; // cUSDCv3

// ─── Protocol interfaces (minimal, for fork test encoding) ───────────────────

interface IAavePool {
    function supply(address asset, uint256 amount, address onBehalfOf, uint16 referralCode) external;
    function withdraw(address asset, uint256 amount, address to) external returns (uint256);
}

interface ISwapRouter {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function exactInputSingle(ExactInputSingleParams calldata params) external payable returns (uint256 amountOut);
}

interface IComet {
    function supply(address asset, uint256 amount) external;
    function withdraw(address asset, uint256 amount) external;
    function balanceOf(address account) external view returns (uint256);
}
