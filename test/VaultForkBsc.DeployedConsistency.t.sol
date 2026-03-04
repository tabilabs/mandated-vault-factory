// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";

import {VaultFactory} from "../src/VaultFactory.sol";

import {BSC_CHAIN_ID, BSC_BUSD} from "./helpers/BscForkConstants.sol";
import {BscTestnetDeploymentJson} from "./helpers/BscTestnetDeploymentJson.sol";

contract VaultForkBscDeployedConsistencyTest is Test {
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

        if (block.chainid != BSC_CHAIN_ID) {
            vm.skip(true, "unexpected chainid: expected BSC testnet fork");
            return;
        }
    }

    function test_bscFork_deployedConsistency_factory_venus_pancake() public view {
        BscTestnetDeploymentJson.Config memory cfg = BscTestnetDeploymentJson.read(vm);

        assertGt(cfg.factory.code.length, 0, "factory code missing");

        bytes32 actualFactoryCodehash = cfg.factory.codehash;
        assertEq(actualFactoryCodehash, cfg.factoryExpectedCodehash, "factory codehash mismatch");

        bytes32 expectedFactoryLeaf = keccak256(abi.encode(cfg.factory, cfg.factoryExpectedCodehash));
        assertEq(expectedFactoryLeaf, cfg.factoryExpectedLeaf, "factory leaf mismatch");

        _assertAdapterConsistency(cfg.venus, "venus");
        _assertAdapterConsistency(cfg.pancake, "pancakeswap");
    }

    function test_bscFork_smoke_deployedFactory_predictMatchesCreate() public {
        BscTestnetDeploymentJson.Config memory cfg = BscTestnetDeploymentJson.read(vm);
        VaultFactory deployedFactory = VaultFactory(cfg.factory);

        address creator = address(0xCAFE);
        address authority = address(0xA11CE);
        bytes32 salt = keccak256("DEPLOYED_FACTORY_SMOKE");

        string memory name = "BSC Deployed Vault";
        string memory symbol = "bdVAULT";

        address predicted = deployedFactory.predictVaultAddress(creator, BSC_BUSD, name, symbol, authority, salt);

        vm.prank(creator);
        address created = deployedFactory.createVault(BSC_BUSD, name, symbol, authority, salt);

        assertEq(created, predicted, "predicted vault mismatch");
        assertGt(created.code.length, 0, "created vault missing code");
    }

    function _assertAdapterConsistency(BscTestnetDeploymentJson.AdapterConfig memory adapterCfg, string memory name)
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
