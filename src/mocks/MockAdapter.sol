// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {IERC4626} from "@openzeppelin/contracts/interfaces/IERC4626.sol";

/// @title MockAdapter
/// @notice A simple adapter for testing MandatedVaultClone execution.
contract MockAdapter {
    event Executed(address indexed vault, bytes data, uint256 value);

    /// @notice Simply emits an event. Used for basic execution tests.
    function doNothing() external payable {
        emit Executed(msg.sender, msg.data, msg.value);
    }

    /// @notice Transfers ERC-20 tokens from the vault (caller) to a recipient.
    function transferToken(address token, address to, uint256 amount) external {
        (bool ok, bytes memory ret) = token.call(abi.encodeWithSignature("transfer(address,uint256)", to, amount));
        require(ok && (ret.length == 0 || abi.decode(ret, (bool))), "transfer failed");
    }

    /// @notice A function that always reverts, for testing failure paths.
    function alwaysReverts() external pure {
        revert("MockAdapter: forced revert");
    }

    receive() external payable {}
}

/// @title DrainAdapter
/// @notice Adapter that drains tokens from the vault for drawdown tests.
contract DrainAdapter {
    function drain(address token, address from, uint256 amount) external {
        (bool ok,) = token.call(abi.encodeWithSignature("burn(address,uint256)", from, amount));
        require(ok, "drain failed");
    }

    receive() external payable {}
}

/// @title MockERC1271Authority
/// @notice Implements ERC-1271 isValidSignature for testing smart contract authorities.
/// @dev Uses ECDSA internally to validate signatures against a stored signer key.
contract MockERC1271Authority {
    bytes4 internal constant _ERC1271_MAGICVALUE = 0x1626ba7e;
    address public immutable signer;

    constructor(address signer_) {
        signer = signer_;
    }

    function isValidSignature(bytes32 hash, bytes calldata signature) external view returns (bytes4) {
        // Recover signer from ECDSA signature
        require(signature.length == 65, "bad sig len");
        bytes32 r;
        bytes32 s;
        uint8 v;
        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 0x20))
            v := byte(0, calldataload(add(signature.offset, 0x40)))
        }
        address recovered = ecrecover(hash, v, r, s);
        if (recovered == signer) {
            return _ERC1271_MAGICVALUE;
        }
        return 0xffffffff;
    }
}

/// @title RejectingERC1271Authority
/// @notice Always rejects signatures (returns wrong magic value).
contract RejectingERC1271Authority {
    function isValidSignature(bytes32, bytes calldata) external pure returns (bytes4) {
        return 0xffffffff;
    }
}

/// @title AuthorityHijackAdapter
/// @notice Calls vault.acceptAuthority() during execution to test authority cache.
contract AuthorityHijackAdapter {
    event Executed(address indexed vault);

    function hijackAuthority(address vault) external {
        // This adapter IS the pendingAuthority, so acceptAuthority() will succeed
        (bool ok,) = vault.call(abi.encodeWithSignature("acceptAuthority()"));
        require(ok, "acceptAuthority failed");
        emit Executed(vault);
    }

    function doNothing() external {}
}

/// @title LargeRevertAdapter
/// @notice Reverts with oversized return data (8 KiB) to test truncation.
contract LargeRevertAdapter {
    function revertLarge() external pure {
        assembly {
            // Allocate 8192 bytes of zeroed memory and revert with it.
            // Content doesn't matter — the test only checks truncated length.
            revert(0, 8192)
        }
    }
}

/// @title ShortReturnAuthority
/// @notice Returns correct ERC-1271 magic value but in only 4 bytes (not ABI-encoded 32 bytes).
/// @dev Tests the `gt(returndatasize(), 0x1f)` defense in _verifyAuthoritySig.
contract ShortReturnAuthority {
    fallback() external payable {
        assembly {
            // Return 0x1626ba7e (correct magic) but only 4 bytes, not 32
            mstore(0, 0x1626ba7e00000000000000000000000000000000000000000000000000000000)
            return(0, 4)
        }
    }
}

/// @title GasBurningAdapter
/// @notice Adapter that intentionally burns gas then reverts, for gas-griefing stress tests.
contract GasBurningAdapter {
    function burnGasAndRevert(uint256 loops) external pure {
        uint256 acc;
        for (uint256 i = 0; i < loops;) {
            acc += i;
            unchecked {
                ++i;
            }
        }
        if (acc >= 0) revert("burned");
    }
}

/// @title VaultBusyAttackAdapter
/// @notice Attempts ERC-4626 operations on the vault during execute() to test VaultBusy reentrancy guard.
contract VaultBusyAttackAdapter {
    function tryMint(address vault, uint256 shares) external {
        IERC4626(vault).mint(shares, address(this));
    }

    function tryWithdraw(address vault, uint256 assets) external {
        IERC4626(vault).withdraw(assets, address(this), address(this));
    }

    function tryRedeem(address vault, uint256 shares) external {
        IERC4626(vault).redeem(shares, address(this), address(this));
    }
}
