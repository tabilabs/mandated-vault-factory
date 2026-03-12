// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {VaultFactory} from "../src/VaultFactory.sol";

contract DeployFactory is Script {
    function run() external returns (VaultFactory factory) {
        uint256 expectedChainId = vm.envUint("EXPECTED_CHAIN_ID");
        require(block.chainid == expectedChainId, "unexpected chain id");

        vm.startBroadcast();
        factory = new VaultFactory();
        vm.stopBroadcast();

        console2.log("FACTORY_ADDRESS", address(factory));
    }
}
