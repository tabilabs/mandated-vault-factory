// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

// --- Fork configuration ---
uint256 constant BSC_MAINNET_CHAIN_ID = 56;
uint256 constant BSC_MAINNET_FORK_BLOCK = 0;

// --- Tokens ---
address constant BSC_MAINNET_BUSD = 0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56;
address constant BSC_MAINNET_USDT = 0x55d398326f99059fF775485246999027B3197955;
address constant BSC_MAINNET_WBNB = 0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c;

// --- Venus Core Pool ---
address constant BSC_MAINNET_VENUS_COMPTROLLER = 0xfD36E2c2a6789Db23113685031d7F16329158384;
address constant BSC_MAINNET_VBUSD = 0x95c78222B3D6e262426483D42CfA53685A67Ab9D;
address constant BSC_MAINNET_VUSDT = 0xfD5840Cd36d94D7229439859C0112a4185BC0255;

// --- PancakeSwap V3 ---
address constant BSC_MAINNET_PANCAKESWAP_V3_ROUTER = 0x1b81D678ffb9C0263b24A97847620C99d213eB14;
address constant BSC_MAINNET_PANCAKESWAP_V3_FACTORY = 0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865;
address constant BSC_MAINNET_PANCAKESWAP_QUOTER_V2 = 0xB048Bbc1Ee6b733FFfCFb9e9CeF7375518e25997;
uint24 constant BSC_MAINNET_BUSD_WBNB_FEE = 2500;

interface IVenusComptrollerLike {
    function getAllMarkets() external view returns (address[] memory);
}

interface IVTokenLike {
    function underlying() external view returns (address);
}

interface IPancakeSwapV3RouterLike {
    function factory() external view returns (address);
    function WETH9() external view returns (address);
}

interface IPancakeV3FactoryLike {
    function getPool(address tokenA, address tokenB, uint24 fee) external view returns (address);
}
