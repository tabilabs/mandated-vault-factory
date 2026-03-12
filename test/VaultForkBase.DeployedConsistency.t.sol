// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

import {BASE_CHAIN_ID} from "./helpers/BaseForkConstants.sol";
import {BaseDeploymentJson} from "./helpers/BaseDeploymentJson.sol";

contract VaultForkBaseDeployedConsistencyTest is Test {
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

    function test_baseFork_deployedConsistency_factory_top5Adapters() public {
        if (!BaseDeploymentJson.isComplete(vm)) {
            vm.skip(true, "base-mainnet deployment record incomplete: protocol anchors exist, project deployment not filled");
            return;
        }

        BaseDeploymentJson.Config memory cfg = BaseDeploymentJson.read(vm);

        assertGt(cfg.factory.code.length, 0, "factory code missing");

        bytes32 actualFactoryCodehash = cfg.factory.codehash;
        assertEq(actualFactoryCodehash, cfg.factoryExpectedCodehash, "factory codehash mismatch");

        bytes32 expectedFactoryLeaf = keccak256(abi.encode(cfg.factory, cfg.factoryExpectedCodehash));
        assertEq(expectedFactoryLeaf, cfg.factoryExpectedLeaf, "factory leaf mismatch");

        _assertAdapterConsistency(cfg.aave, "aave");
        _assertAdapterConsistency(cfg.morpho, "morpho");
        _assertAdapterConsistency(cfg.uniswap, "uniswap");
        _assertAdapterConsistency(cfg.aerodrome, "aerodrome");
        _assertAdapterConsistency(cfg.compound, "compound");
    }

    function _assertAdapterConsistency(BaseDeploymentJson.AdapterConfig memory adapterCfg, string memory name)
        internal
        view
    {
        assertGt(adapterCfg.adapter.code.length, 0, string.concat(name, " adapter code missing"));

        bytes32 actualCodehash = adapterCfg.adapter.codehash;
        assertEq(actualCodehash, adapterCfg.expectedCodehash, string.concat(name, " codehash mismatch"));

        bytes32 expectedLeaf = keccak256(abi.encode(adapterCfg.adapter, adapterCfg.expectedCodehash));
        assertEq(expectedLeaf, adapterCfg.expectedLeaf, string.concat(name, " leaf mismatch"));
    }
}
