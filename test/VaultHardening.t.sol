// SPDX-License-Identifier: CC0-1.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";

import {VaultFactory} from "../src/VaultFactory.sol";
import {MandatedVaultClone} from "../src/MandatedVaultClone.sol";
import {IERCXXXXMandatedVault} from "../src/interfaces/IERCXXXXMandatedVault.sol";
import {MockAdapter} from "../src/mocks/MockAdapter.sol";

contract HardeningToken is ERC20 {
    constructor() ERC20("Hardening Token", "HARD") {}

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}

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

contract VaultBusyAttackAdapter {
    function tryMint(address vault, uint256 shares) external {
        MandatedVaultClone(payable(vault)).mint(shares, address(this));
    }

    function tryWithdraw(address vault, uint256 assets) external {
        MandatedVaultClone(payable(vault)).withdraw(assets, address(this), address(this));
    }

    function tryRedeem(address vault, uint256 shares) external {
        MandatedVaultClone(payable(vault)).redeem(shares, address(this), address(this));
    }
}

contract VaultHardeningTest is Test {
    VaultFactory public factory;
    HardeningToken public token;
    MockAdapter public adapter;
    GasBurningAdapter public gasBurner;
    VaultBusyAttackAdapter public busyAttacker;

    uint256 internal authorityKey = 0xA11CE;
    address internal authority;
    address internal creator = address(0xC0);
    address internal executor = address(0xE0);

    function setUp() public {
        authority = vm.addr(authorityKey);
        token = new HardeningToken();
        factory = new VaultFactory();
        adapter = new MockAdapter();
        gasBurner = new GasBurningAdapter();
        busyAttacker = new VaultBusyAttackAdapter();
    }

    function _createVault() internal returns (MandatedVaultClone v) {
        vm.prank(creator);
        v = MandatedVaultClone(payable(factory.createVault(address(token), "HV", "HV", authority, bytes32(0))));
        token.mint(address(v), 1_000_000e18);
    }

    function _singleLeafRoot(address a) internal view returns (bytes32) {
        return keccak256(abi.encode(a, a.codehash));
    }

    function _mandate(MandatedVaultClone v, uint256 nonce, bytes32 root, bytes memory extensions)
        internal
        view
        returns (IERCXXXXMandatedVault.Mandate memory)
    {
        return IERCXXXXMandatedVault.Mandate({
            executor: executor,
            nonce: nonce,
            deadline: 0,
            authorityEpoch: v.authorityEpoch(),
            maxDrawdownBps: 500,
            maxCumulativeDrawdownBps: 1000,
            allowedAdaptersRoot: root,
            payloadDigest: bytes32(0),
            extensionsHash: keccak256(extensions)
        });
    }

    function _sign(MandatedVaultClone v, IERCXXXXMandatedVault.Mandate memory m) internal view returns (bytes memory) {
        (uint8 vv, bytes32 r, bytes32 s) = vm.sign(authorityKey, v.hashMandate(m));
        return abi.encodePacked(r, s, vv);
    }

    function _proofs1() internal pure returns (bytes32[][] memory p) {
        p = new bytes32[][](1);
        p[0] = new bytes32[](0);
    }

    function test_supportsExtension_unknown_returnsFalse() public {
        MandatedVaultClone v = _createVault();
        assertEq(v.supportsExtension(bytes4(0x12345678)), false);
    }

    function test_execute_optionalUnknownExtension_succeeds() public {
        MandatedVaultClone v = _createVault();

        IERCXXXXMandatedVault.Extension[] memory exts = new IERCXXXXMandatedVault.Extension[](1);
        exts[0] = IERCXXXXMandatedVault.Extension(bytes4(0xabcdef01), false, bytes(""));
        bytes memory extensions = abi.encode(exts);

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(address(adapter), 0, abi.encodeCall(MockAdapter.doNothing, ()));

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0, _singleLeafRoot(address(adapter)), extensions);
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        (uint256 pre, uint256 post) = v.execute(m, actions, sig, _proofs1(), extensions);
        assertEq(pre, post, "no-op action with optional unknown extension should succeed");
    }

    function test_actionCallFailed_gasBurningAdapter() public {
        MandatedVaultClone v = _createVault();

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(
            address(gasBurner), 0, abi.encodeCall(GasBurningAdapter.burnGasAndRevert, (60_000))
        );

        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0, _singleLeafRoot(address(gasBurner)), "");
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        vm.expectPartialRevert(IERCXXXXMandatedVault.ActionCallFailed.selector);
        v.execute(m, actions, sig, _proofs1(), "");
    }

    function test_vaultBusy_mintDuringExecute() public {
        MandatedVaultClone v = _createVault();

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(
            address(busyAttacker), 0, abi.encodeCall(VaultBusyAttackAdapter.tryMint, (address(v), 1e18))
        );

        _expectVaultBusyInner(v, actions, _singleLeafRoot(address(busyAttacker)));
    }

    function test_vaultBusy_withdrawDuringExecute() public {
        MandatedVaultClone v = _createVault();

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(
            address(busyAttacker), 0, abi.encodeCall(VaultBusyAttackAdapter.tryWithdraw, (address(v), 1e18))
        );

        _expectVaultBusyInner(v, actions, _singleLeafRoot(address(busyAttacker)));
    }

    function test_vaultBusy_redeemDuringExecute() public {
        MandatedVaultClone v = _createVault();

        IERCXXXXMandatedVault.Action[] memory actions = new IERCXXXXMandatedVault.Action[](1);
        actions[0] = IERCXXXXMandatedVault.Action(
            address(busyAttacker), 0, abi.encodeCall(VaultBusyAttackAdapter.tryRedeem, (address(v), 1e18))
        );

        _expectVaultBusyInner(v, actions, _singleLeafRoot(address(busyAttacker)));
    }

    function _expectVaultBusyInner(MandatedVaultClone v, IERCXXXXMandatedVault.Action[] memory actions, bytes32 root)
        internal
    {
        IERCXXXXMandatedVault.Mandate memory m = _mandate(v, 0, root, "");
        bytes memory sig = _sign(v, m);

        vm.prank(executor);
        try v.execute(m, actions, sig, _proofs1(), "") {
            revert("expected revert");
        } catch (bytes memory revertData) {
            assertGt(revertData.length, 4, "revert data too short");
            assertEq(bytes4(revertData), IERCXXXXMandatedVault.ActionCallFailed.selector, "wrong outer selector");

            (uint256 actionIndex, bytes memory innerReason) = abi.decode(_stripSelector(revertData), (uint256, bytes));
            assertEq(actionIndex, 0, "wrong action index");
            assertEq(bytes4(innerReason), IERCXXXXMandatedVault.VaultBusy.selector, "inner reason should be VaultBusy");
        }
    }

    function _stripSelector(bytes memory data) internal pure returns (bytes memory payload) {
        payload = new bytes(data.length - 4);
        for (uint256 i = 0; i < payload.length; i++) {
            payload[i] = data[i + 4];
        }
    }
}
