// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {IERC8192MandatedVault} from "../src/interfaces/IERC8192MandatedVault.sol";
import {PancakeSwapV3Adapter} from "../src/adapters/PancakeSwapV3Adapter.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";

import {BSC_BUSD, BSC_WBNB, BSC_BUSD_WBNB_FEE} from "./helpers/BscForkConstants.sol";
import {VaultForkBscBase} from "./VaultForkBsc.Base.t.sol";
import {BscTestnetDeploymentJson} from "./helpers/BscTestnetDeploymentJson.sol";

contract VaultForkBscPancakeTest is VaultForkBscBase {
    function test_bscFork_smoke_pancake_swap_busd_to_wbnb() public {
        BscTestnetDeploymentJson.Config memory cfg = BscTestnetDeploymentJson.read(vm);

        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 amountIn = 1_000e18;
        deal(BSC_BUSD, address(v), amountIn);

        (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
            _rootForPair(BSC_BUSD, cfg.pancake.adapter);

        IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
        actions[0] =
            IERC8192MandatedVault.Action(BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (cfg.pancake.adapter, amountIn)));
        actions[1] = IERC8192MandatedVault.Action(
            cfg.pancake.adapter,
            0,
            abi.encodeCall(
                PancakeSwapV3Adapter.swap, (BSC_BUSD, BSC_WBNB, BSC_BUSD_WBNB_FEE, block.timestamp + 300, amountIn, 1)
            )
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = busdProof;
        proofs[1] = adapterProof;

        IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        (bool ok, bytes memory ret) = _execRaw(v, m, actions, proofs);
        if (!ok) {
            assertEq(_revertSelector(ret), IERC8192MandatedVault.ActionCallFailed.selector, "unexpected selector");
            (uint256 idx, bytes memory reason) = _decodeActionCallFailed(ret);
            assertEq(idx, 1, "unexpected failing action");
            if (_isPancakeProtocolUnavailable(reason)) {
                vm.skip(
                    true,
                    _unavailableMessage("pancake swap unavailable on current fork head", BSC_BUSD, BSC_WBNB, reason)
                );
                return;
            }
            revert(_unavailableMessage("pancake swap failed (not protocol issue)", BSC_BUSD, BSC_WBNB, reason));
        }

        assertEq(IERC20(BSC_BUSD).balanceOf(address(v)), 0, "BUSD should be spent");
        assertGt(IERC20(BSC_WBNB).balanceOf(address(v)), 0, "WBNB should be received");
    }

    function test_bscFork_deterministic_pancake_swap_revert_deadlineExpired() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 amountIn = 1_000e18;
        deal(BSC_BUSD, address(v), amountIn);

        (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
            _rootForPair(BSC_BUSD, address(pancakeAdapter));

        IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
        actions[0] = IERC8192MandatedVault.Action(
            BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(pancakeAdapter), amountIn))
        );
        actions[1] = IERC8192MandatedVault.Action(
            address(pancakeAdapter),
            0,
            abi.encodeCall(
                PancakeSwapV3Adapter.swap, (BSC_BUSD, BSC_WBNB, BSC_BUSD_WBNB_FEE, block.timestamp - 1, amountIn, 1)
            )
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = busdProof;
        proofs[1] = adapterProof;

        IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(IERC8192MandatedVault.ActionCallFailed.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    function test_bscFork_deterministic_pancake_swap_revert_slippage() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 amountIn = 1_000e18;
        deal(BSC_BUSD, address(v), amountIn);

        (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
            _rootForPair(BSC_BUSD, address(pancakeAdapter));

        IERC8192MandatedVault.Action[] memory actions = new IERC8192MandatedVault.Action[](2);
        actions[0] = IERC8192MandatedVault.Action(
            BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(pancakeAdapter), amountIn))
        );
        actions[1] = IERC8192MandatedVault.Action(
            address(pancakeAdapter),
            0,
            abi.encodeCall(
                PancakeSwapV3Adapter.swap,
                (BSC_BUSD, BSC_WBNB, BSC_BUSD_WBNB_FEE, block.timestamp + 300, amountIn, type(uint256).max)
            )
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = busdProof;
        proofs[1] = adapterProof;

        IERC8192MandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(IERC8192MandatedVault.ActionCallFailed.selector);
        v.execute(m, actions, sig, proofs, "");
    }
}
