// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";
import {PancakeSwapV3Adapter} from "../src/adapters/PancakeSwapV3Adapter.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";

import {BSC_BUSD, BSC_WBNB, BSC_BUSD_WBNB_FEE} from "./helpers/BscForkConstants.sol";
import {VaultForkBscBase} from "./VaultForkBsc.Base.t.sol";

contract VaultForkBscPancakeTest is VaultForkBscBase {
    function test_bscFork_smoke_pancake_swap_busd_to_wbnb() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 amountIn = 1_000e18;
        deal(BSC_BUSD, address(v), amountIn);

        (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
            _rootForPair(BSC_BUSD, address(pancakeAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(
            BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(pancakeAdapter), amountIn))
        );
        actions[1] = IERCXXXXMandatedVault.Action(
            address(pancakeAdapter),
            0,
            abi.encodeCall(
                PancakeSwapV3Adapter.swap, (BSC_BUSD, BSC_WBNB, BSC_BUSD_WBNB_FEE, block.timestamp + 300, amountIn, 1)
            )
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = busdProof;
        proofs[1] = adapterProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        _exec(v, m, actions, proofs);

        assertEq(IERC20(BSC_BUSD).balanceOf(address(v)), 0, "BUSD should be spent");
        assertGt(IERC20(BSC_WBNB).balanceOf(address(v)), 0, "WBNB should be received");
    }

    function test_bscFork_deterministic_pancake_swap_revert_deadlineExpired() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 amountIn = 1_000e18;
        deal(BSC_BUSD, address(v), amountIn);

        (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
            _rootForPair(BSC_BUSD, address(pancakeAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(
            BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(pancakeAdapter), amountIn))
        );
        actions[1] = IERCXXXXMandatedVault.Action(
            address(pancakeAdapter),
            0,
            abi.encodeCall(
                PancakeSwapV3Adapter.swap, (BSC_BUSD, BSC_WBNB, BSC_BUSD_WBNB_FEE, block.timestamp - 1, amountIn, 1)
            )
        );

        bytes32[][] memory proofs = new bytes32[][](2);
        proofs[0] = busdProof;
        proofs[1] = adapterProof;

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(IERCXXXXMandatedVault.ActionCallFailed.selector);
        v.execute(m, actions, sig, proofs, "");
    }

    function test_bscFork_deterministic_pancake_swap_revert_slippage() public {
        MandatedVaultClone v = _createVault(BSC_BUSD);
        uint256 amountIn = 1_000e18;
        deal(BSC_BUSD, address(v), amountIn);

        (bytes32 root, bytes32[] memory busdProof, bytes32[] memory adapterProof) =
            _rootForPair(BSC_BUSD, address(pancakeAdapter));

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](2);
        actions[0] = IERCXXXXMandatedVault.Action(
            BSC_BUSD, 0, abi.encodeCall(IERC20.approve, (address(pancakeAdapter), amountIn))
        );
        actions[1] = IERCXXXXMandatedVault.Action(
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

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, _nextNonce(), 10000, root);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(IERCXXXXMandatedVault.ActionCallFailed.selector);
        v.execute(m, actions, sig, proofs, "");
    }
}
