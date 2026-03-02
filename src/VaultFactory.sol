// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Clones} from "@openzeppelin/contracts/proxy/Clones.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {MandatedVaultClone} from "./MandatedVaultClone.sol";
import {IVaultFactory} from "./interfaces/IVaultFactory.sol";

/// @title VaultFactory
/// @notice Deploys ERC-1167 minimal proxy instances of MandatedVaultClone.
/// @dev Fully immutable (no owner, no admin, no upgradability). Uses CREATE2 via
///      `Clones.cloneDeterministic` for deterministic vault addresses. The CREATE2 salt
///      incorporates `msg.sender` to prevent front-running of vault deployments.
///
///      Deployment flow:
///      1. Factory constructor deploys a locked MandatedVaultClone implementation.
///      2. `createVault()` clones the implementation and calls `initialize()`.
///      3. Vault addresses are predictable via `predictVaultAddress()`.
contract VaultFactory is IVaultFactory {
    /// @inheritdoc IVaultFactory
    address public immutable implementation;

    uint256 private _vaultCount;
    mapping(address => bool) private _isVault;
    mapping(address => address[]) private _vaultsByCreator;

    /// @dev Deploys a locked MandatedVaultClone as the implementation template.
    ///      The implementation's constructor calls `_disableInitializers()`,
    ///      permanently preventing direct initialization.
    constructor() {
        implementation = address(new MandatedVaultClone());
    }

    /// @inheritdoc IVaultFactory
    function createVault(address asset, string calldata name, string calldata symbol, address authority, bytes32 salt)
        external
        returns (address vault)
    {
        bytes32 actualSalt = _computeSalt(msg.sender, asset, name, symbol, authority, salt);
        vault = Clones.cloneDeterministic(implementation, actualSalt);

        MandatedVaultClone(payable(vault)).initialize(IERC20(asset), name, symbol, authority);

        _isVault[vault] = true;
        _vaultsByCreator[msg.sender].push(vault);
        _vaultCount++;

        emit VaultCreated(vault, msg.sender, authority, asset, name, symbol);
    }

    /// @inheritdoc IVaultFactory
    function isVault(address vault) external view returns (bool) {
        return _isVault[vault];
    }

    /// @inheritdoc IVaultFactory
    function getVaultsByCreator(address creator) external view returns (address[] memory) {
        return _vaultsByCreator[creator];
    }

    /// @inheritdoc IVaultFactory
    function vaultCount() external view returns (uint256) {
        return _vaultCount;
    }

    /// @inheritdoc IVaultFactory
    /// @dev The predicted address depends on `msg.sender` because the salt
    ///      includes the caller. For on-chain composability, use the overloaded
    ///      version with an explicit `creator` parameter.
    function predictVaultAddress(
        address asset,
        string calldata name,
        string calldata symbol,
        address authority,
        bytes32 salt
    ) external view returns (address) {
        bytes32 actualSalt = _computeSalt(msg.sender, asset, name, symbol, authority, salt);
        return Clones.predictDeterministicAddress(implementation, actualSalt);
    }

    /// @notice Predicts the deterministic address of a vault for a specific creator.
    /// @dev Enables on-chain composability — other contracts can predict vault addresses
    ///      without needing to be the creator. Does NOT weaken CREATE2 front-running
    ///      protection (creation still uses `msg.sender`).
    function predictVaultAddress(
        address creator,
        address asset,
        string calldata name,
        string calldata symbol,
        address authority,
        bytes32 salt
    ) external view returns (address) {
        bytes32 actualSalt = _computeSalt(creator, asset, name, symbol, authority, salt);
        return Clones.predictDeterministicAddress(implementation, actualSalt);
    }

    /// @dev Computes the CREATE2 salt from all deployment parameters.
    ///      Including `creator` prevents front-running: an attacker cannot
    ///      deploy the same vault at the predicted address before the intended creator.
    function _computeSalt(
        address creator,
        address asset,
        string calldata name,
        string calldata symbol,
        address authority,
        bytes32 salt
    ) internal pure returns (bytes32) {
        return keccak256(abi.encode(creator, asset, name, symbol, authority, salt));
    }
}
