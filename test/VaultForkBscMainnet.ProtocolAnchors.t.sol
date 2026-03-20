// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

import {
    BSC_MAINNET_CHAIN_ID,
    BSC_MAINNET_BUSD,
    BSC_MAINNET_USDT,
    BSC_MAINNET_WBNB,
    BSC_MAINNET_VENUS_COMPTROLLER,
    BSC_MAINNET_VBUSD,
    BSC_MAINNET_VUSDT,
    BSC_MAINNET_PANCAKESWAP_V3_ROUTER,
    BSC_MAINNET_PANCAKESWAP_V3_FACTORY,
    BSC_MAINNET_PANCAKESWAP_QUOTER_V2,
    BSC_MAINNET_BUSD_WBNB_FEE,
    IVenusComptrollerLike,
    IVTokenLike,
    IPancakeSwapV3RouterLike,
    IPancakeV3FactoryLike
} from "./helpers/BscMainnetForkConstants.sol";

contract VaultForkBscMainnetProtocolAnchorsTest is Test {
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

        if (block.chainid != BSC_MAINNET_CHAIN_ID) {
            vm.skip(true, "unexpected chainid: expected BSC mainnet fork");
            return;
        }
    }

    function test_bscMainnetFork_protocolAnchors_haveRuntimeCode() public view {
        assertGt(BSC_MAINNET_BUSD.code.length, 0, "BUSD missing code");
        assertGt(BSC_MAINNET_USDT.code.length, 0, "USDT missing code");
        assertGt(BSC_MAINNET_WBNB.code.length, 0, "WBNB missing code");
        assertGt(BSC_MAINNET_VENUS_COMPTROLLER.code.length, 0, "Venus comptroller missing code");
        assertGt(BSC_MAINNET_VBUSD.code.length, 0, "vBUSD missing code");
        assertGt(BSC_MAINNET_VUSDT.code.length, 0, "vUSDT missing code");
        assertGt(BSC_MAINNET_PANCAKESWAP_V3_ROUTER.code.length, 0, "Pancake router missing code");
        assertGt(BSC_MAINNET_PANCAKESWAP_V3_FACTORY.code.length, 0, "Pancake factory missing code");
        assertGt(BSC_MAINNET_PANCAKESWAP_QUOTER_V2.code.length, 0, "Pancake quoter missing code");
    }

    function test_bscMainnetFork_protocolAnchors_matchExpectedRelationships() public view {
        assertEq(IVTokenLike(BSC_MAINNET_VBUSD).underlying(), BSC_MAINNET_BUSD, "vBUSD underlying mismatch");
        assertEq(IVTokenLike(BSC_MAINNET_VUSDT).underlying(), BSC_MAINNET_USDT, "vUSDT underlying mismatch");
        assertEq(
            IPancakeSwapV3RouterLike(BSC_MAINNET_PANCAKESWAP_V3_ROUTER).factory(),
            BSC_MAINNET_PANCAKESWAP_V3_FACTORY,
            "Pancake factory mismatch"
        );
        assertEq(
            IPancakeSwapV3RouterLike(BSC_MAINNET_PANCAKESWAP_V3_ROUTER).WETH9(),
            BSC_MAINNET_WBNB,
            "Pancake WBNB mismatch"
        );
    }

    function test_bscMainnetFork_protocolAnchors_venusMarketsContainTrackedAssets() public view {
        address[] memory markets = IVenusComptrollerLike(BSC_MAINNET_VENUS_COMPTROLLER).getAllMarkets();
        assertGt(markets.length, 0, "Venus markets empty");
        assertTrue(_contains(markets, BSC_MAINNET_VBUSD), "vBUSD missing from Venus markets");
        assertTrue(_contains(markets, BSC_MAINNET_VUSDT), "vUSDT missing from Venus markets");
    }

    function test_bscMainnetFork_protocolAnchors_haveTrackedPool() public view {
        address pool = IPancakeV3FactoryLike(BSC_MAINNET_PANCAKESWAP_V3_FACTORY)
            .getPool(BSC_MAINNET_BUSD, BSC_MAINNET_WBNB, BSC_MAINNET_BUSD_WBNB_FEE);
        assertGt(pool.code.length, 0, "Pancake BUSD/WBNB pool missing");
    }

    function _contains(address[] memory items, address target) internal pure returns (bool) {
        for (uint256 i = 0; i < items.length; ++i) {
            if (items[i] == target) return true;
        }
        return false;
    }
}
