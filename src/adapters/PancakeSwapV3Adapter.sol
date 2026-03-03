// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

interface IPancakeSwapV3Router {
    struct ExactInputSingleParams {
        address tokenIn;
        address tokenOut;
        uint24 fee;
        address recipient;
        uint256 deadline;
        uint256 amountIn;
        uint256 amountOutMinimum;
        uint160 sqrtPriceLimitX96;
    }

    function exactInputSingle(ExactInputSingleParams calldata params) external returns (uint256 amountOut);
}

/// @title PancakeSwapV3Adapter
/// @notice Minimal adapter for PancakeSwap V3 single-hop swaps.
/// @dev Interface-compatible with Uniswap V3 SwapRouter exactInputSingle.
contract PancakeSwapV3Adapter {
    using SafeERC20 for IERC20;

    address public immutable router;

    error ZeroAddressRouter();
    error ZeroAddressToken();
    error IdenticalTokenPair();
    error ZeroAmount();
    error ZeroFee();
    error DeadlineExpired(uint256 deadline, uint256 currentTimestamp);

    event Swapped(
        address indexed caller,
        address indexed tokenIn,
        address indexed tokenOut,
        uint24 fee,
        uint256 amountIn,
        uint256 amountOut,
        uint256 amountOutMinimum,
        uint256 deadline
    );

    constructor(address router_) {
        if (router_ == address(0)) revert ZeroAddressRouter();
        router = router_;
    }

    /// @notice Swaps tokenIn to tokenOut and sends output to caller.
    /// @param tokenIn Input token address.
    /// @param tokenOut Output token address.
    /// @param fee Pool fee (e.g. 2500 = 0.25%).
    /// @param deadline Swap expiration timestamp (unix seconds).
    /// @param amountIn Input token amount.
    /// @param amountOutMinimum Minimum amount out for slippage protection.
    /// @return amountOut Output token amount.
    function swap(
        address tokenIn,
        address tokenOut,
        uint24 fee,
        uint256 deadline,
        uint256 amountIn,
        uint256 amountOutMinimum
    ) external returns (uint256 amountOut) {
        if (tokenIn == address(0) || tokenOut == address(0)) revert ZeroAddressToken();
        if (tokenIn == tokenOut) revert IdenticalTokenPair();
        if (amountIn == 0) revert ZeroAmount();
        if (fee == 0) revert ZeroFee();
        if (deadline < block.timestamp) revert DeadlineExpired(deadline, block.timestamp);

        IERC20 tokenInAsset = IERC20(tokenIn);
        uint256 balanceBefore = tokenInAsset.balanceOf(address(this));
        tokenInAsset.safeTransferFrom(msg.sender, address(this), amountIn);
        tokenInAsset.forceApprove(router, amountIn);

        IPancakeSwapV3Router.ExactInputSingleParams memory params = IPancakeSwapV3Router.ExactInputSingleParams({
            tokenIn: tokenIn,
            tokenOut: tokenOut,
            fee: fee,
            recipient: msg.sender,
            deadline: deadline,
            amountIn: amountIn,
            amountOutMinimum: amountOutMinimum,
            sqrtPriceLimitX96: 0
        });

        amountOut = IPancakeSwapV3Router(router).exactInputSingle(params);
        tokenInAsset.forceApprove(router, 0);

        uint256 balanceAfter = tokenInAsset.balanceOf(address(this));
        uint256 remainingTokenIn = balanceAfter - balanceBefore;
        if (remainingTokenIn > 0) {
            tokenInAsset.safeTransfer(msg.sender, remainingTokenIn);
        }

        emit Swapped(msg.sender, tokenIn, tokenOut, fee, amountIn, amountOut, amountOutMinimum, deadline);
    }
}
