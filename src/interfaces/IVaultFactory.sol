// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

/// @title IVaultFactory
/// @notice Interface for the ownerless ERC-1167 Clone factory that deploys MandatedVaultClone instances.
interface IVaultFactory {
    /// @notice Emitted when a new vault clone is created.
    /// @param vault The address of the newly created vault.
    /// @param creator The address that called createVault.
    /// @param authority The initial authority of the vault.
    /// @param asset The ERC-20 underlying asset of the vault.
    /// @param name The ERC-20 name of the vault share token.
    /// @param symbol The ERC-20 symbol of the vault share token.
    event VaultCreated(
        address indexed vault,
        address indexed creator,
        address indexed authority,
        address asset,
        string name,
        string symbol
    );

    /// @notice Deploys a new MandatedVaultClone via CREATE2.
    /// @param asset The ERC-20 underlying asset address.
    /// @param name The ERC-20 name for the vault share token.
    /// @param symbol The ERC-20 symbol for the vault share token.
    /// @param authority The initial authority address for the vault.
    /// @param salt A user-provided salt for deterministic address derivation.
    /// @return vault The address of the newly deployed vault.
    function createVault(address asset, string calldata name, string calldata symbol, address authority, bytes32 salt)
        external
        returns (address vault);

    /// @notice Returns whether an address is a factory-deployed vault.
    /// @param vault The address to check.
    /// @return True if the address was deployed by this factory.
    function isVault(address vault) external view returns (bool);

    /// @notice Returns all vault addresses created by a given creator.
    /// @param creator The creator address to query.
    /// @return An array of vault addresses.
    function getVaultsByCreator(address creator) external view returns (address[] memory);

    /// @notice Returns the implementation contract address used for cloning.
    /// @return The implementation address.
    function implementation() external view returns (address);

    /// @notice Returns the total number of vaults deployed by this factory.
    /// @return The vault count.
    function vaultCount() external view returns (uint256);

    /// @notice Predicts the vault address for the given parameters (uses msg.sender as creator).
    /// @param asset The ERC-20 underlying asset address.
    /// @param name The ERC-20 name for the vault share token.
    /// @param symbol The ERC-20 symbol for the vault share token.
    /// @param authority The initial authority address.
    /// @param salt The user-provided salt.
    /// @return The predicted vault address.
    function predictVaultAddress(
        address asset,
        string calldata name,
        string calldata symbol,
        address authority,
        bytes32 salt
    ) external view returns (address);

    /// @notice Predicts the vault address for a specific creator (for on-chain composability).
    /// @param creator The creator address to use in salt derivation.
    /// @param asset The ERC-20 underlying asset address.
    /// @param name The ERC-20 name for the vault share token.
    /// @param symbol The ERC-20 symbol for the vault share token.
    /// @param authority The initial authority address.
    /// @param salt The user-provided salt.
    /// @return The predicted vault address.
    function predictVaultAddress(
        address creator,
        address asset,
        string calldata name,
        string calldata symbol,
        address authority,
        bytes32 salt
    ) external view returns (address);
}
