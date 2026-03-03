// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

// --- Fork configuration ---
uint256 constant BSC_CHAIN_ID = 97;
uint256 constant BSC_FORK_BLOCK = 93_533_855;

// --- Tokens ---
// PancakeSwap test token set
address constant BSC_BUSD = 0xeD24FC36d5Ee211Ea25A80239Fb8C4Cfd80f12Ee;
address constant BSC_USDT = 0x337610d27c682E347C9cD60BD4b3b107C9d34dDd;
address constant BSC_WBNB = 0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd;

// --- Venus ---
address constant BSC_VENUS_COMPTROLLER = 0x94d1820b2D1c7c7452A163983Dc888CEC546b77D;
address constant BSC_VBUSD = 0x08e0A5575De71037aE36AbfAfb516595fE68e5e4;
address constant BSC_VUSDT = 0xb7526572FFE56AB9D7489838Bf2E18e3323b441A;
// Underlyings queried from vToken.underlying()
address constant BSC_VENUS_BUSD_UNDERLYING = 0x8301F2213c0eeD49a7E28Ae4c3e91722919B8B47;
address constant BSC_VENUS_USDT_UNDERLYING = 0xA11c8D9DC9b66E209Ef60F0C8D969D3CD988782c;

// --- PancakeSwap V3 ---
address constant BSC_PANCAKESWAP_V3_ROUTER = 0x1b81D678ffb9C0263b24A97847620C99d213eB14;
address constant BSC_PANCAKESWAP_V3_FACTORY = 0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865;
uint24 constant BSC_BUSD_WBNB_FEE = 2500;

interface IVenusComptroller {
    function getAllMarkets() external view returns (address[] memory);
}
