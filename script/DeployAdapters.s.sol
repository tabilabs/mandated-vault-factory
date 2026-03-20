// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {VenusAdapter} from "../src/adapters/VenusAdapter.sol";
import {PancakeSwapV3Adapter} from "../src/adapters/PancakeSwapV3Adapter.sol";

contract DeployAdapters is Script {
    address internal constant DEFAULT_PANCAKESWAP_V3_ROUTER = 0x1b81D678ffb9C0263b24A97847620C99d213eB14;

    function run() external returns (VenusAdapter venusAdapter, PancakeSwapV3Adapter pancakeSwapV3Adapter) {
        uint256 expectedChainId = vm.envUint("EXPECTED_CHAIN_ID");
        require(block.chainid == expectedChainId, "unexpected chain id");

        address router = _envOrAddress("PANCAKESWAP_V3_ROUTER", DEFAULT_PANCAKESWAP_V3_ROUTER);

        vm.startBroadcast();
        venusAdapter = new VenusAdapter();
        pancakeSwapV3Adapter = new PancakeSwapV3Adapter(router);
        vm.stopBroadcast();

        console2.log("VENUS_ADAPTER_ADDRESS", address(venusAdapter));
        console2.log("PANCAKESWAP_ADAPTER_ADDRESS", address(pancakeSwapV3Adapter));
        console2.log("PANCAKESWAP_V3_ROUTER", router);
    }

    function _envOrAddress(string memory envKey, address fallbackValue) internal view returns (address value) {
        try vm.envAddress(envKey) returns (address configured) {
            value = configured;
        } catch {
            value = fallbackValue;
        }
    }
}
