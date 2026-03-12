// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {stdJson} from "forge-std/StdJson.sol";
import {Vm} from "forge-std/Vm.sol";

library BaseDeploymentJson {
    using stdJson for string;

    string internal constant FILE_PATH = "deployments/base-mainnet.json";

    struct AdapterConfig {
        address adapter;
        bytes32 expectedCodehash;
        bytes32 expectedLeaf;
    }

    struct Config {
        address factory;
        bytes32 factoryExpectedCodehash;
        bytes32 factoryExpectedLeaf;
        AdapterConfig aave;
        AdapterConfig morpho;
        AdapterConfig uniswap;
        AdapterConfig aerodrome;
        AdapterConfig compound;
    }

    function isComplete(Vm vm) internal view returns (bool) {
        string memory raw = vm.readFile(FILE_PATH);
        return isCompleteRaw(raw);
    }

    function isCompleteRaw(string memory raw) internal view returns (bool) {
        return !_isPlaceholder(raw.readStringOr(".factory", ""))
            && !_isPlaceholder(raw.readStringOr(".factoryCodehash", ""))
            && !_isPlaceholder(raw.readStringOr(".factoryLeaf", ""))
            && !_isPlaceholder(raw.readStringOr(".adapters.aave", ""))
            && !_isPlaceholder(raw.readStringOr(".adapters.morpho", ""))
            && !_isPlaceholder(raw.readStringOr(".adapters.uniswap", ""))
            && !_isPlaceholder(raw.readStringOr(".adapters.aerodrome", ""))
            && !_isPlaceholder(raw.readStringOr(".adapters.compound", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterCodehashes.aave", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterCodehashes.morpho", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterCodehashes.uniswap", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterCodehashes.aerodrome", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterCodehashes.compound", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterLeaves.aave", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterLeaves.morpho", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterLeaves.uniswap", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterLeaves.aerodrome", ""))
            && !_isPlaceholder(raw.readStringOr(".adapterLeaves.compound", ""));
    }

    function read(Vm vm) internal view returns (Config memory cfg) {
        string memory raw = vm.readFile(FILE_PATH);

        string memory factoryRaw = raw.readString(".factory");
        string memory factoryCodehashRaw = raw.readString(".factoryCodehash");
        string memory factoryLeafRaw = raw.readString(".factoryLeaf");

        string memory aaveRaw = raw.readString(".adapters.aave");
        string memory morphoRaw = raw.readString(".adapters.morpho");
        string memory uniswapRaw = raw.readString(".adapters.uniswap");
        string memory aerodromeRaw = raw.readString(".adapters.aerodrome");
        string memory compoundRaw = raw.readString(".adapters.compound");

        string memory aaveCodehashRaw = raw.readString(".adapterCodehashes.aave");
        string memory morphoCodehashRaw = raw.readString(".adapterCodehashes.morpho");
        string memory uniswapCodehashRaw = raw.readString(".adapterCodehashes.uniswap");
        string memory aerodromeCodehashRaw = raw.readString(".adapterCodehashes.aerodrome");
        string memory compoundCodehashRaw = raw.readString(".adapterCodehashes.compound");

        string memory aaveLeafRaw = raw.readString(".adapterLeaves.aave");
        string memory morphoLeafRaw = raw.readString(".adapterLeaves.morpho");
        string memory uniswapLeafRaw = raw.readString(".adapterLeaves.uniswap");
        string memory aerodromeLeafRaw = raw.readString(".adapterLeaves.aerodrome");
        string memory compoundLeafRaw = raw.readString(".adapterLeaves.compound");

        require(!_isPlaceholder(factoryRaw), "deployment json incomplete: factory");
        require(!_isPlaceholder(factoryCodehashRaw), "deployment json incomplete: factoryCodehash");
        require(!_isPlaceholder(factoryLeafRaw), "deployment json incomplete: factoryLeaf");
        require(!_isPlaceholder(aaveRaw), "deployment json incomplete: adapters.aave");
        require(!_isPlaceholder(morphoRaw), "deployment json incomplete: adapters.morpho");
        require(!_isPlaceholder(uniswapRaw), "deployment json incomplete: adapters.uniswap");
        require(!_isPlaceholder(aerodromeRaw), "deployment json incomplete: adapters.aerodrome");
        require(!_isPlaceholder(compoundRaw), "deployment json incomplete: adapters.compound");
        require(!_isPlaceholder(aaveCodehashRaw), "deployment json incomplete: adapterCodehashes.aave");
        require(!_isPlaceholder(morphoCodehashRaw), "deployment json incomplete: adapterCodehashes.morpho");
        require(!_isPlaceholder(uniswapCodehashRaw), "deployment json incomplete: adapterCodehashes.uniswap");
        require(!_isPlaceholder(aerodromeCodehashRaw), "deployment json incomplete: adapterCodehashes.aerodrome");
        require(!_isPlaceholder(compoundCodehashRaw), "deployment json incomplete: adapterCodehashes.compound");
        require(!_isPlaceholder(aaveLeafRaw), "deployment json incomplete: adapterLeaves.aave");
        require(!_isPlaceholder(morphoLeafRaw), "deployment json incomplete: adapterLeaves.morpho");
        require(!_isPlaceholder(uniswapLeafRaw), "deployment json incomplete: adapterLeaves.uniswap");
        require(!_isPlaceholder(aerodromeLeafRaw), "deployment json incomplete: adapterLeaves.aerodrome");
        require(!_isPlaceholder(compoundLeafRaw), "deployment json incomplete: adapterLeaves.compound");

        cfg.factory = vm.parseAddress(factoryRaw);
        cfg.factoryExpectedCodehash = vm.parseBytes32(factoryCodehashRaw);
        cfg.factoryExpectedLeaf = vm.parseBytes32(factoryLeafRaw);

        cfg.aave.adapter = vm.parseAddress(aaveRaw);
        cfg.aave.expectedCodehash = vm.parseBytes32(aaveCodehashRaw);
        cfg.aave.expectedLeaf = vm.parseBytes32(aaveLeafRaw);

        cfg.morpho.adapter = vm.parseAddress(morphoRaw);
        cfg.morpho.expectedCodehash = vm.parseBytes32(morphoCodehashRaw);
        cfg.morpho.expectedLeaf = vm.parseBytes32(morphoLeafRaw);

        cfg.uniswap.adapter = vm.parseAddress(uniswapRaw);
        cfg.uniswap.expectedCodehash = vm.parseBytes32(uniswapCodehashRaw);
        cfg.uniswap.expectedLeaf = vm.parseBytes32(uniswapLeafRaw);

        cfg.aerodrome.adapter = vm.parseAddress(aerodromeRaw);
        cfg.aerodrome.expectedCodehash = vm.parseBytes32(aerodromeCodehashRaw);
        cfg.aerodrome.expectedLeaf = vm.parseBytes32(aerodromeLeafRaw);

        cfg.compound.adapter = vm.parseAddress(compoundRaw);
        cfg.compound.expectedCodehash = vm.parseBytes32(compoundCodehashRaw);
        cfg.compound.expectedLeaf = vm.parseBytes32(compoundLeafRaw);
    }

    function _isPlaceholder(string memory value) private pure returns (bool) {
        bytes memory b = bytes(value);
        if (b.length == 0) return true;
        if (b[0] == bytes1("<")) return true;
        return false;
    }
}
