// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {stdJson} from "forge-std/StdJson.sol";
import {Vm} from "forge-std/Vm.sol";

library BscTestnetDeploymentJson {
    using stdJson for string;

    string internal constant FILE_PATH = "deployments/bsc-testnet.json";

    struct AdapterConfig {
        address adapter;
        bytes32 expectedCodehash;
        bytes32 expectedLeaf;
    }

    struct Config {
        address factory;
        bytes32 factoryExpectedCodehash;
        bytes32 factoryExpectedLeaf;
        AdapterConfig venus;
        AdapterConfig pancake;
    }

    function read(Vm vm) internal view returns (Config memory cfg) {
        string memory raw = vm.readFile(FILE_PATH);

        string memory factoryRaw = raw.readString(".factory");
        string memory factoryCodehashRaw = raw.readString(".factoryCodehash");
        string memory factoryLeafRaw = raw.readString(".factoryLeaf");
        string memory venusRaw = raw.readString(".adapters.venus");
        string memory pancakeRaw = raw.readString(".adapters.pancakeswap");
        string memory venusCodehashRaw = raw.readString(".adapterCodehashes.venus");
        string memory pancakeCodehashRaw = raw.readString(".adapterCodehashes.pancakeswap");
        string memory venusLeafRaw = raw.readString(".adapterLeaves.venus");
        string memory pancakeLeafRaw = raw.readString(".adapterLeaves.pancakeswap");

        require(!_isPlaceholder(factoryRaw), "deployment json incomplete: factory");
        require(!_isPlaceholder(factoryCodehashRaw), "deployment json incomplete: factoryCodehash");
        require(!_isPlaceholder(factoryLeafRaw), "deployment json incomplete: factoryLeaf");
        require(!_isPlaceholder(venusRaw), "deployment json incomplete: adapters.venus");
        require(!_isPlaceholder(pancakeRaw), "deployment json incomplete: adapters.pancakeswap");
        require(!_isPlaceholder(venusCodehashRaw), "deployment json incomplete: adapterCodehashes.venus");
        require(!_isPlaceholder(pancakeCodehashRaw), "deployment json incomplete: adapterCodehashes.pancakeswap");
        require(!_isPlaceholder(venusLeafRaw), "deployment json incomplete: adapterLeaves.venus");
        require(!_isPlaceholder(pancakeLeafRaw), "deployment json incomplete: adapterLeaves.pancakeswap");

        cfg.factory = vm.parseAddress(factoryRaw);
        cfg.factoryExpectedCodehash = vm.parseBytes32(factoryCodehashRaw);
        cfg.factoryExpectedLeaf = vm.parseBytes32(factoryLeafRaw);

        cfg.venus.adapter = vm.parseAddress(venusRaw);
        cfg.venus.expectedCodehash = vm.parseBytes32(venusCodehashRaw);
        cfg.venus.expectedLeaf = vm.parseBytes32(venusLeafRaw);

        cfg.pancake.adapter = vm.parseAddress(pancakeRaw);
        cfg.pancake.expectedCodehash = vm.parseBytes32(pancakeCodehashRaw);
        cfg.pancake.expectedLeaf = vm.parseBytes32(pancakeLeafRaw);
    }

    function _isPlaceholder(string memory value) private pure returns (bool) {
        bytes memory b = bytes(value);
        if (b.length == 0) return true;
        if (b[0] == bytes1("<")) return true;
        return false;
    }
}
