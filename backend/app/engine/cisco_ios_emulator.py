"""
Emulador y parser interactivo de comandos Cisco IOS para NetTutorIA.
Permite ejecutar comandos en tiempo real sobre la configuración activa del dispositivo:
- enable / disable
- configure terminal / exit / end
- interface <nombre> (incluye subinterfaces dot1Q como Fa0/0.10)
- switchport mode trunk / access
- switchport access vlan <id>
- switchport trunk native vlan <id>
- switchport trunk allowed vlan <lista>
- encapsulation dot1Q <vlan>
- ip address <ip> <mask>
- shutdown / no shutdown
- ip default-gateway <ip>
- ip route <net> <mask> <nexthop>
- show running-config / show ip interface brief / show vlan brief
"""

import re
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.core.models import Device, DeviceType, Interface, InterfaceStatus, SwitchportMode


class CommandExecutionRequest(BaseModel):
    device_id: str
    command: str
    current_mode: str = "user" # user (>), priv (#), config (config)#, config-if (config-if)#
    current_interface: Optional[str] = None


class CommandExecutionResponse(BaseModel):
    output: str
    new_mode: str
    prompt: str
    current_interface: Optional[str] = None
    configuration_changed: bool = False


class CiscoIOSEmulator:

    @classmethod
    def execute(cls, device: Device, req: CommandExecutionRequest) -> CommandExecutionResponse:
        cmd = req.command.strip()
        mode = req.current_mode
        curr_if_name = req.current_interface
        prompt_prefix = device.name

        if not cmd:
            return CommandExecutionResponse(
                output="",
                new_mode=mode,
                prompt=cls._get_prompt(prompt_prefix, mode, curr_if_name),
                current_interface=curr_if_name,
                configuration_changed=False
            )

        cmd_lower = cmd.lower()
        changed = False
        output = ""

        # Comandos de navegación de modos
        if cmd_lower in ("enable", "en"):
            mode = "priv"
        elif cmd_lower in ("disable", "exit", "quit") and mode == "priv":
            mode = "user"
        elif cmd_lower in ("configure terminal", "conf t", "config t") and mode == "priv":
            mode = "config"
            output = "Enter configuration commands, one per line. End with CNTL/Z."
        elif cmd_lower in ("exit", "end") and mode == "config":
            mode = "priv"
        elif cmd_lower == "end" and mode == "config-if":
            mode = "priv"
            curr_if_name = None
        elif cmd_lower == "exit" and mode == "config-if":
            mode = "config"
            curr_if_name = None

        # Modo CONFIG
        elif mode == "config":
            if cmd_lower.startswith("interface ") or cmd_lower.startswith("int "):
                if_name = cmd.split(maxsplit=1)[1]
                # Normalizar nombre
                norm_if = cls._find_or_create_interface(device, if_name)
                curr_if_name = norm_if.name
                mode = "config-if"
            elif cmd_lower.startswith("hostname "):
                new_h = cmd.split()[1]
                device.name = new_h
                prompt_prefix = new_h
                changed = True
            elif cmd_lower.startswith("ip default-gateway "):
                device.default_gateway = cmd.split()[2]
                changed = True
            elif cmd_lower.startswith("ip route "):
                parts = cmd.split()
                if len(parts) >= 5:
                    device.static_routes.append({
                        "network": parts[2],
                        "mask": parts[3],
                        "next_hop": parts[4]
                    })
                    changed = True
            elif cmd_lower.startswith("no ip route "):
                parts = cmd.split()
                if len(parts) >= 6:
                    device.static_routes = [
                        r for r in device.static_routes
                        if not (r.get("network") == parts[3] and r.get("mask") == parts[4])
                    ]
                    changed = True
            else:
                output = "% Incomplete or unrecognized command."

        # Modo CONFIG-IF
        elif mode == "config-if":
            target_if = next((i for i in device.interfaces if i.name == curr_if_name), None)
            if not target_if:
                output = "% Interface context error."
            else:
                if cmd_lower in ("shutdown", "shut"):
                    target_if.status = InterfaceStatus.ADMIN_DOWN
                    output = f"%LINK-5-CHANGED: Interface {target_if.name}, changed state to administratively down"
                    changed = True
                elif cmd_lower in ("no shutdown", "no shut"):
                    target_if.status = InterfaceStatus.UP
                    output = f"%LINK-5-CHANGED: Interface {target_if.name}, changed state to up"
                    changed = True
                elif cmd_lower.startswith("ip address ") or cmd_lower.startswith("ip add "):
                    parts = cmd.split()
                    if len(parts) >= 4:
                        target_if.ip_address = parts[2]
                        target_if.subnet_mask = parts[3]
                        changed = True
                elif cmd_lower in ("no ip address", "no ip add"):
                    target_if.ip_address = None
                    target_if.subnet_mask = None
                    changed = True
                elif cmd_lower == "switchport mode trunk":
                    target_if.switchport_mode = SwitchportMode.TRUNK
                    changed = True
                elif cmd_lower == "switchport mode access":
                    target_if.switchport_mode = SwitchportMode.ACCESS
                    changed = True
                elif cmd_lower.startswith("switchport access vlan "):
                    vid = int(cmd.split()[3])
                    target_if.access_vlan = vid
                    target_if.switchport_mode = SwitchportMode.ACCESS
                    changed = True
                elif cmd_lower.startswith("switchport trunk native vlan "):
                    vid = int(cmd.split()[4])
                    target_if.native_vlan = vid
                    changed = True
                elif cmd_lower.startswith("switchport trunk allowed vlan "):
                    spec = cmd.split(maxsplit=4)[4]
                    v_list = []
                    for p in spec.split(","):
                        if "-" in p:
                            s, e = p.split("-")
                            v_list.extend(range(int(s), int(e)+1))
                        elif p.isdigit():
                            v_list.append(int(p))
                    target_if.trunk_allowed_vlans = sorted(set(v_list))
                    changed = True
                elif cmd_lower.startswith("encapsulation dot1q "):
                    vid = int(cmd.split()[2])
                    target_if.encapsulation_dot1q = vid
                    changed = True
                else:
                    output = "% Incomplete or unrecognized interface command."

        # Comandos SHOW en cualquier modo EXEC
        if cmd_lower in ("show ip interface brief", "sh ip int br", "do show ip interface brief"):
            output = cls._render_ip_int_brief(device)
        elif cmd_lower in ("show running-config", "sh run", "do show running-config", "do sh run"):
            output = cls._render_running_config(device)

        return CommandExecutionResponse(
            output=output,
            new_mode=mode,
            prompt=cls._get_prompt(prompt_prefix, mode, curr_if_name),
            current_interface=curr_if_name,
            configuration_changed=changed
        )

    @staticmethod
    def _get_prompt(hostname: str, mode: str, if_name: Optional[str]) -> str:
        if mode == "user":
            return f"{hostname}>"
        if mode == "priv":
            return f"{hostname}#"
        if mode == "config":
            return f"{hostname}(config)#"
        if mode == "config-if":
            short_if = if_name.replace("FastEthernet", "Fa").replace("GigabitEthernet", "Gi") if if_name else ""
            return f"{hostname}(config-if)#{' ' if not short_if else ''}"
        return f"{hostname}#"

    @staticmethod
    def _find_or_create_interface(device: Device, name_input: str) -> Interface:
        # Match case-insensitive
        clean = name_input.strip()
        for i in device.interfaces:
            if i.name.lower() == clean.lower():
                return i
            if clean.lower().startswith("fa") and "fastethernet" in i.name.lower() and i.name.lower().endswith(clean[2:].lower()):
                return i
            if clean.lower().startswith("gi") and "gigabitethernet" in i.name.lower() and i.name.lower().endswith(clean[2:].lower()):
                return i

        # Si es subinterfaz nueva dot1Q (e.g. Fa0/0.10)
        new_if = Interface(name=clean, status=InterfaceStatus.UP)
        device.interfaces.append(new_if)
        return new_if

    @staticmethod
    def _render_ip_int_brief(device: Device) -> str:
        lines = [
            f"{'Interface':<25} {'IP-Address':<16} {'OK?':<5} {'Method':<8} {'Status':<16} {'Protocol'}",
            f"{'-'*25} {'-'*16} {'-'*5} {'-'*8} {'-'*16} {'-'*8}"
        ]
        for i in device.interfaces:
            ip_str = i.ip_address or "unassigned"
            status_str = "up" if i.status == InterfaceStatus.UP else "administratively down"
            proto_str = "up" if i.status == InterfaceStatus.UP else "down"
            lines.append(f"{i.name:<25} {ip_str:<16} {'YES':<5} {'manual':<8} {status_str:<16} {proto_str}")
        return "\n".join(lines)

    @staticmethod
    def _render_running_config(device: Device) -> str:
        lines = [
            f"hostname {device.name}",
            "!"
        ]
        for vid, vname in (device.vlans or {}).items():
            lines.extend([f"vlan {vid}", f" name {vname}", "!"])

        for i in device.interfaces:
            lines.append(f"interface {i.name}")
            if i.encapsulation_dot1q:
                lines.append(f" encapsulation dot1Q {i.encapsulation_dot1q}")
            if i.ip_address and i.subnet_mask:
                lines.append(f" ip address {i.ip_address} {i.subnet_mask}")
            if i.switchport_mode == SwitchportMode.TRUNK:
                lines.append(" switchport mode trunk")
                if i.native_vlan and i.native_vlan != 1:
                    lines.append(f" switchport trunk native vlan {i.native_vlan}")
                if i.trunk_allowed_vlans:
                    lines.append(f" switchport trunk allowed vlan {','.join(str(v) for v in i.trunk_allowed_vlans)}")
            elif i.switchport_mode == SwitchportMode.ACCESS:
                lines.append(" switchport mode access")
                if i.access_vlan and i.access_vlan != 1:
                    lines.append(f" switchport access vlan {i.access_vlan}")
            if i.status == InterfaceStatus.ADMIN_DOWN:
                lines.append(" shutdown")
            lines.append("!")

        if device.default_gateway:
            lines.append(f"ip default-gateway {device.default_gateway}")

        for r in (device.static_routes or []):
            lines.append(f"ip route {r.get('network')} {r.get('mask')} {r.get('next_hop')}")

        lines.append("end")
        return "\n".join(lines)

