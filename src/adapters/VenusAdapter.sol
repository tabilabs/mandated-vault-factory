// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

interface IVToken {
    function mint(uint256 mintAmount) external returns (uint256);
    function redeem(uint256 redeemTokens) external returns (uint256);
    function underlying() external view returns (address);
}

/// @title VenusAdapter
/// @notice Minimal adapter for supplying/redeeming assets on Venus-compatible vToken markets.
/// @dev Designed to be called by MandatedVaultClone as an adapter action target.
contract VenusAdapter {
    using SafeERC20 for IERC20;

    error ZeroAddressVToken();
    error ZeroAddressUnderlying();
    error ZeroAmount();
    error InsufficientUnderlyingAllowanceFromCaller(uint256 allowance, uint256 required);
    error InsufficientUnderlyingAllowanceToMarket(uint256 allowance, uint256 required);
    error InsufficientVTokenAllowanceFromCaller(uint256 allowance, uint256 required);
    error VenusMintFailed(uint256 errorCode);
    error VenusRedeemFailed(uint256 errorCode);
    error ZeroMintOutput();
    error ZeroRedeemOutput();

    event Supplied(
        address indexed caller,
        address indexed vToken,
        address indexed underlying,
        uint256 suppliedAmount,
        uint256 mintedAmount
    );
    event Withdrawn(
        address indexed caller,
        address indexed vToken,
        address indexed underlying,
        uint256 redeemedVTokenAmount,
        uint256 underlyingOut
    );

    /// @notice Supplies underlying to a Venus market and sends minted vTokens back to caller.
    /// @param vToken Venus market token address (e.g. vBUSD).
    /// @param amount Amount of underlying to supply.
    /// @return mintedAmount Amount of vTokens minted and transferred back.
    function supply(address vToken, uint256 amount) external returns (uint256 mintedAmount) {
        if (vToken == address(0)) revert ZeroAddressVToken();
        if (amount == 0) revert ZeroAmount();

        address underlying = IVToken(vToken).underlying();
        if (underlying == address(0)) revert ZeroAddressUnderlying();

        IERC20 underlyingToken = IERC20(underlying);
        IERC20 vTokenAsset = IERC20(vToken);

        uint256 beforeBalance = vTokenAsset.balanceOf(address(this));
        uint256 allowanceFromCaller = underlyingToken.allowance(msg.sender, address(this));
        if (allowanceFromCaller < amount) {
            revert InsufficientUnderlyingAllowanceFromCaller(allowanceFromCaller, amount);
        }

        underlyingToken.safeTransferFrom(msg.sender, address(this), amount);
        underlyingToken.forceApprove(vToken, amount);
        uint256 allowanceToMarket = underlyingToken.allowance(address(this), vToken);
        if (allowanceToMarket < amount) revert InsufficientUnderlyingAllowanceToMarket(allowanceToMarket, amount);

        uint256 errorCode = IVToken(vToken).mint(amount);
        if (errorCode != 0) revert VenusMintFailed(errorCode);
        underlyingToken.forceApprove(vToken, 0);

        uint256 afterBalance = vTokenAsset.balanceOf(address(this));
        mintedAmount = afterBalance - beforeBalance;
        if (mintedAmount == 0) revert ZeroMintOutput();
        vTokenAsset.safeTransfer(msg.sender, mintedAmount);
        emit Supplied(msg.sender, vToken, underlying, amount, mintedAmount);
    }

    /// @notice Redeems vTokens on Venus and sends underlying back to caller.
    /// @param vToken Venus market token address.
    /// @param vTokenAmount Amount of vTokens to redeem.
    /// @return underlyingOut Amount of underlying transferred back.
    function withdraw(address vToken, uint256 vTokenAmount) external returns (uint256 underlyingOut) {
        if (vToken == address(0)) revert ZeroAddressVToken();
        if (vTokenAmount == 0) revert ZeroAmount();

        address underlying = IVToken(vToken).underlying();
        if (underlying == address(0)) revert ZeroAddressUnderlying();

        IERC20 underlyingToken = IERC20(underlying);
        IERC20 vTokenAsset = IERC20(vToken);

        uint256 beforeUnderlying = underlyingToken.balanceOf(address(this));
        uint256 allowanceFromCaller = vTokenAsset.allowance(msg.sender, address(this));
        if (allowanceFromCaller < vTokenAmount) {
            revert InsufficientVTokenAllowanceFromCaller(allowanceFromCaller, vTokenAmount);
        }

        vTokenAsset.safeTransferFrom(msg.sender, address(this), vTokenAmount);

        uint256 errorCode = IVToken(vToken).redeem(vTokenAmount);
        if (errorCode != 0) revert VenusRedeemFailed(errorCode);

        uint256 afterUnderlying = underlyingToken.balanceOf(address(this));
        underlyingOut = afterUnderlying - beforeUnderlying;
        if (underlyingOut == 0) revert ZeroRedeemOutput();
        underlyingToken.safeTransfer(msg.sender, underlyingOut);
        emit Withdrawn(msg.sender, vToken, underlying, vTokenAmount, underlyingOut);
    }
}
