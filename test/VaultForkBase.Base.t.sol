// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";

import {
    BASE_CHAIN_ID,
    BASE_USDC,
    BASE_WETH,
    BASE_UNISWAP_QUOTER_V2,
    IQuoterV2Like
} from "./helpers/BaseForkConstants.sol";
import {MerkleHelper} from "./helpers/MerkleHelper.sol";

/// @title VaultForkBaseBase
/// @notice Shared Base mainnet fork setup and mandate helpers for focused Base fork tests.
abstract contract VaultForkBaseBase is Test {
    VaultFactory internal factory;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);
    address internal bob = address(0xB0B);

    uint256 internal nonceCounter;
    bool internal rolledToPinnedBlock;

    function setUp() public virtual {
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

        rolledToPinnedBlock = false;
        if (vm.envExists("BASE_FORK_BLOCK")) {
            uint256 forkBlock = vm.envUint("BASE_FORK_BLOCK");
            if (forkBlock != 0 && block.number != forkBlock) {
                try vm.rollFork(forkBlock) {
                    rolledToPinnedBlock = true;
                } catch {
                    vm.skip(true, "failed to roll fork to BASE_FORK_BLOCK; default mode uses latest head");
                    return;
                }
            }
        }

        if (BASE_USDC.code.length == 0 || BASE_WETH.code.length == 0) {
            vm.skip(true, "Base fork infra failure: cannot read core Base token state");
            return;
        }

        authority = vm.addr(authorityKey);
        factory = new VaultFactory();
    }

    function _nextNonce() internal returns (uint256) {
        return nonceCounter++;
    }

    function _createVault(address asset) internal returns (MandatedVaultClone v) {
        vm.prank(creator);
        v = MandatedVaultClone(
            payable(factory.createVault(asset, "Base Fork Vault", "basefVAULT", authority, bytes32(nonceCounter)))
        );
    }

    function _sign(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m) internal view returns (bytes memory) {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(authorityKey, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    function _leaf(address addr) internal view returns (bytes32) {
        return keccak256(abi.encode(addr, addr.codehash));
    }

    function _rootForPair(address left, address right)
        internal
        view
        returns (bytes32 root, bytes32[] memory leftProof, bytes32[] memory rightProof)
    {
        return MerkleHelper.buildTree2(_leaf(left), _leaf(right));
    }

    function _mandate(MandatedVaultClone v, uint256 nonce, uint16 maxDrawdownBps, bytes32 adaptersRoot)
        internal
        view
        returns (IERCXXXXMandatedVault.Mandate memory)
    {
        return IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0, // 0 = no mandate expiry; fork smoke focuses on protocol integration rather than time-bounded auth UX.
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: maxDrawdownBps,
            maxCumulativeDrawdownBps: maxDrawdownBps,
            allowedAdaptersRoot: adaptersRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
    }

    function _unwindMandate(MandatedVaultClone v, uint256 nonce, bytes32 adaptersRoot)
        internal
        view
        returns (IERCXXXXMandatedVault.Mandate memory)
    {
        return IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 0,
            maxCumulativeDrawdownBps: 10000,
            allowedAdaptersRoot: adaptersRoot,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256("")
        });
    }

    function _exec(
        MandatedVaultClone v,
        IERCXXXXMandatedVault.Mandate memory m,
        IERCXXXXMandatedVault.Action[] memory actions,
        bytes32[][] memory proofs
    ) internal returns (uint256 pre, uint256 post) {
        bytes memory sig = _sign(v, m);
        vm.prank(executor);
        return v.execute(m, actions, sig, proofs, "");
    }

    function _quoteUniswapExactInputSingle(address tokenIn, address tokenOut, uint256 amountIn, uint24 fee)
        internal
        returns (uint256 amountOut)
    {
        IQuoterV2Like.QuoteExactInputSingleParams memory params = IQuoterV2Like.QuoteExactInputSingleParams({
            tokenIn: tokenIn, tokenOut: tokenOut, amountIn: amountIn, fee: fee, sqrtPriceLimitX96: 0
        });

        (amountOut,,,) = IQuoterV2Like(BASE_UNISWAP_QUOTER_V2).quoteExactInputSingle(params);
    }

    function _depositToVault(MandatedVaultClone v, address asset, uint256 amount) internal {
        deal(asset, bob, amount);

        vm.startPrank(bob);
        IERC20(asset).approve(address(v), amount);
        v.deposit(amount, bob);
        vm.stopPrank();
    }

    function _redeemAllShares(MandatedVaultClone v) internal returns (uint256 assetsOut) {
        uint256 shares = v.balanceOf(bob);
        vm.prank(bob);
        assetsOut = v.redeem(shares, bob, bob);
    }
}
