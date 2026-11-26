"""
Reglas de diagnóstico basadas en el cuadro de instrucciones de archivos .PKA (Packet Tracer Activity).
Analiza las tablas de direccionamiento HTML y el texto de las instrucciones embebidas en
`topology.activity_instructions` para contrastar el estado actual de los dispositivos contra
los requisitos reales de la práctica (DHCP en PCs, IPs/Máscaras/Gateways de la tabla, VLANs, OSPF).
"""

import re
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple
from app.core.models import (
    Topology,
    Device,
    DeviceType,
    Interface,
    DiagnosticFinding,
    DiagnosticSeverity,
)

_IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_CIDR_RE = re.compile(r"\b((?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d))/(\d{1,2})\b")


class _SimpleTableParser(HTMLParser):
    """Extrae todas las tablas HTML como listas de filas (listas de textos de celdas)."""

    def __init__(self):
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._curr_table: List[List[str]] = []
        self._curr_row: List[str] = []
        self._curr_cell: List[str] = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "table":
            self._in_table = True
            self._curr_table = []
        elif t == "tr" and self._in_table:
            self._in_row = True
            self._curr_row = []
        elif t in ("td", "th") and self._in_row:
            self._in_cell = True
            self._curr_cell = []

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ("td", "th") and self._in_cell:
            text = re.sub(r"\s+", " ", "".join(self._curr_cell)).strip()
            self._curr_row.append(text)
            self._in_cell = False
        elif t == "tr" and self._in_row:
            if any(c for c in self._curr_row):
                self._curr_table.append(self._curr_row)
            self._in_row = False
        elif t == "table" and self._in_table:
            if self._curr_table:
                self.tables.append(self._curr_table)
            self._in_table = False

    def handle_data(self, data):
        if self._in_cell:
            self._curr_cell.append(data)


def _canonical_if_name(name: str) -> str:
    n = (name or "").strip().lower().replace(" ", "")
    n = re.sub(r"^fastethernet", "fa", n)
    n = re.sub(r"^gigabitethernet", "gi", n)
    n = re.sub(r"^tengigabitethernet", "te", n)
    n = re.sub(r"^ethernet", "eth", n)
    n = re.sub(r"^serial", "se", n)
    n = re.sub(r"^vlan", "vlan", n)
    n = re.sub(r"^f(\d)", r"fa\1", n)
    n = re.sub(r"^g(\d)", r"gi\1", n)
    n = re.sub(r"^s(\d)", r"se\1", n)
    return n


def _prefix_to_mask(prefix: int) -> Optional[str]:
    if not (0 <= prefix <= 32):
        return None
    bits = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF if prefix > 0 else 0
    return ".".join(str((bits >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def _extract_addressing_rows(html_pages: List[str]) -> List[Dict[str, Optional[str]]]:
    """
    Parsea tablas de direccionamiento HTML (Addressing Table / Tabla de direccionamiento)
    devolviendo filas estructuradas: device, interface, ip, mask, gateway, is_dhcp.
    """
    rows_out: List[Dict[str, Optional[str]]] = []

    for html_str in html_pages:
        parser = _SimpleTableParser()
        try:
            parser.feed(html_str)
        except Exception:
            continue

        for table in parser.tables:
            if len(table) < 2:
                continue

            header = [c.lower() for c in table[0]]
            # Identificar si es una tabla de direccionamiento
            dev_col = next((i for i, h in enumerate(header) if any(k in h for k in ("device", "dispositivo", "equipo", "host"))), None)
            ip_col = next((i for i, h in enumerate(header) if any(k in h for k in ("ip address", "dirección ip", "direccion ip", "ip"))), None)
            if dev_col is None or ip_col is None:
                continue

            if_col = next((i for i, h in enumerate(header) if any(k in h for k in ("interface", "interfaz", "puerto", "port"))), None)
            mask_col = next((i for i, h in enumerate(header) if any(k in h for k in ("subnet", "mask", "máscara", "mascara"))), None)
            gw_col = next((i for i, h in enumerate(header) if any(k in h for k in ("gateway", "puerta de enlace", "enlace predeterminado"))), None)

            last_device_name = ""
            for raw_row in table[1:]:
                if len(raw_row) <= max(dev_col, ip_col):
                    continue
                dev_cell = raw_row[dev_col].strip()
                if dev_cell:
                    last_device_name = dev_cell
                elif last_device_name:
                    dev_cell = last_device_name
                else:
                    continue

                if_cell = raw_row[if_col].strip() if (if_col is not None and if_col < len(raw_row)) else ""
                ip_cell = raw_row[ip_col].strip()
                mask_cell = raw_row[mask_col].strip() if (mask_col is not None and mask_col < len(raw_row)) else ""
                gw_cell = raw_row[gw_col].strip() if (gw_col is not None and gw_col < len(raw_row)) else ""

                is_dhcp = "dhcp" in ip_cell.lower() or "dhcp" in mask_cell.lower()
                ip_val: Optional[str] = None
                mask_val: Optional[str] = None

                cidr_m = _CIDR_RE.search(ip_cell)
                if cidr_m:
                    ip_val = cidr_m.group(1)
                    mask_val = _prefix_to_mask(int(cidr_m.group(2)))
                else:
                    ip_m = _IPV4_RE.search(ip_cell)
                    if ip_m:
                        ip_val = ip_m.group(0)

                if not mask_val:
                    mask_m = _IPV4_RE.search(mask_cell)
                    if mask_m:
                        mask_val = mask_m.group(0)
                    elif mask_cell.startswith("/") and mask_cell[1:].isdigit():
                        mask_val = _prefix_to_mask(int(mask_cell[1:]))

                gw_m = _IPV4_RE.search(gw_cell)
                gw_val = gw_m.group(0) if gw_m else None

                if is_dhcp or ip_val or gw_val:
                    rows_out.append(
                        {
                            "device": dev_cell,
                            "interface": if_cell,
                            "ip": ip_val,
                            "mask": mask_val,
                            "gateway": gw_val,
                            "is_dhcp": "true" if is_dhcp else "false",
                        }
                    )

    return rows_out


def _match_device(devices: List[Device], name_from_table: str) -> Optional[Device]:
    target = name_from_table.strip().lower()
    if not target:
        return None
    # Match exacto primero
    for d in devices:
        if d.name.strip().lower() == target or d.id.strip().lower() == target:
            return d
    # Match removiendo espacios/guiones (ej. "PC-A" vs "PC A" vs "PCA")
    norm_target = re.sub(r"[\s\-_]+", "", target)
    for d in devices:
        if re.sub(r"[\s\-_]+", "", d.name.lower()) == norm_target:
            return d
    return None


def _match_interface(dev: Device, if_from_table: str) -> Optional[Interface]:
    if not if_from_table or if_from_table.lower() in ("nic", "n/a", "na", "-"):
        return dev.interfaces[0] if dev.interfaces else None
    canon = _canonical_if_name(if_from_table)
    for iface in dev.interfaces:
        if iface.name.lower() == if_from_table.lower() or _canonical_if_name(iface.name) == canon:
            return iface
    return None


def _text_requests_dhcp_for_hosts(full_text: str) -> bool:
    """Detecta si las instrucciones textuales del .pka indican que las PCs/hosts deben usar DHCP."""
    t = full_text.lower()
    if "dhcp" not in t:
        return False
    patterns = [
        r"(?:pc|pcs|host|hosts|client|clientes|equipo|equipos|computadora|computadoras)[^.\n]{0,90}\bdhcp\b",
        r"\bdhcp\b[^.\n]{0,90}(?:pc|pcs|host|hosts|client|clientes|equipo|equipos|computadora|computadoras|din[aá]mic|autom[aá]tic|obtener|recibir|receive|obtain)",
        r"(?:recibir|obtener|receive|obtain|assign|asignar)[^.\n]{0,60}(?:ip|direcci[oó]n|address)[^.\n]{0,50}\bdhcp\b",
    ]
    return any(re.search(p, t) for p in patterns)


def check_pka_activity_rules(topology: Topology) -> List[DiagnosticFinding]:
    """
    Evalúa la topología contra las instrucciones embebidas en un archivo .PKA.
    Si la práctica no tiene cuadro de instrucciones (`activity_instructions`), no genera hallazgos.
    """
    if not topology.activity_instructions:
        return []

    findings: List[DiagnosticFinding] = []
    html_pages = [p.get("html", "") for p in topology.activity_instructions if p.get("html")]
    full_text = "\n\n".join(p.get("text", "") for p in topology.activity_instructions if p.get("text"))

    addressing_rows = _extract_addressing_rows(html_pages)
    checked_dhcp_devices: Set[str] = set()
    checked_ip_pairs: Set[Tuple[str, str]] = set()

    # 1. Validar cada fila de la Tabla de Direccionamiento del .PKA
    for row in addressing_rows:
        dev = _match_device(topology.devices, row["device"] or "")
        if not dev:
            continue

        is_dhcp_req = row["is_dhcp"] == "true"
        expected_ip = row["ip"]
        expected_mask = row["mask"]
        expected_gw = row["gateway"]
        if_label = row["interface"] or "NIC"

        # Caso A: La tabla exige DHCP para este host
        if is_dhcp_req and dev.type in (DeviceType.PC, DeviceType.SERVER):
            checked_dhcp_devices.add(dev.id)
            main_if = _match_interface(dev, if_label)
            has_dhcp = bool(main_if and main_if.dhcp_enabled)
            has_ip = bool(main_if and main_if.ip_address and main_if.ip_address != "unassigned")

            if not has_dhcp:
                current_state = (
                    f"actualmente tiene una IP estática ({main_if.ip_address})"
                    if has_ip
                    else "actualmente está en modo Estático sin dirección IP"
                )
                findings.append(
                    DiagnosticFinding(
                        id=f"pka_dhcp_req_{dev.id}",
                        rule_id="RULE_PKA_HOST_DHCP_REQUIRED",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=dev.id,
                        device_name=dev.name,
                        interface_name=main_if.name if main_if else None,
                        title=f"{dev.name} debe obtener su IP por DHCP (según instrucciones .PKA)",
                        description=(
                            f"La tabla de direccionamiento de la actividad indica que {dev.name} debe recibir su "
                            f"dirección IP en modo DHCP, pero {current_state}."
                        ),
                        hint_level1=(
                            f"Revisa la tabla de direccionamiento en las instrucciones de la actividad: "
                            f"¿debe {dev.name} configurarse con IP estática o mediante asignación dinámica?"
                        ),
                        hint_level2=(
                            f"Abre {dev.name} → Desktop → IP Configuration y verifica que el modo de obtención de IP "
                            f"coincida con lo solicitado en la práctica."
                        ),
                        technical_solution=(
                            f"Según las instrucciones de la actividad (.PKA), configura {dev.name} en modo DHCP:\n"
                            f"1. Abre {dev.name} en Packet Tracer.\n"
                            f"2. Ve a la pestaña Desktop → IP Configuration.\n"
                            f"3. Cambia de 'Static' a 'DHCP' y verifica que reciba una IP válida del pool."
                        ),
                    )
                )
            elif not has_ip:
                findings.append(
                    DiagnosticFinding(
                        id=f"pka_dhcp_no_lease_{dev.id}",
                        rule_id="RULE_PKA_HOST_DHCP_NO_LEASE",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=dev.id,
                        device_name=dev.name,
                        interface_name=main_if.name if main_if else None,
                        title=f"{dev.name} está en modo DHCP pero no recibió dirección IP",
                        description=(
                            f"{dev.name} tiene DHCP activado como piden las instrucciones, pero no logró obtener "
                            f"una dirección IP del servidor/router DHCP."
                        ),
                        hint_level1="Si un cliente tiene DHCP activado pero falla la solicitud, ¿qué podría estar impidiendo que los mensajes DHCP Discover lleguen al servidor?",
                        hint_level2=f"Verifica el enlace físico/VLAN de {dev.name}, que el pool DHCP exista en el router/servidor y si hace falta 'ip helper-address' en el gateway.",
                        technical_solution=(
                            f"1. Verifica que el pool DHCP en el router/servidor tenga red y default-router correctos.\n"
                            f"2. Si el servidor DHCP está en otra subred, configura 'ip helper-address <IP_SERVIDOR_DHCP>' en la interfaz gateway del router.\n"
                            f"3. En {dev.name} → Desktop → IP Configuration, vuelve a pulsar 'DHCP' para renovar el lease."
                        ),
                    )
                )
            continue

        # Caso B: La tabla exige una IP estática específica
        if expected_ip:
            iface = _match_interface(dev, if_label)
            pair_key = (dev.id, _canonical_if_name(iface.name if iface else if_label))
            if pair_key in checked_ip_pairs:
                continue
            checked_ip_pairs.add(pair_key)

            actual_ip = iface.ip_address if iface else None
            actual_mask = iface.subnet_mask if iface else None

            ip_mismatch = actual_ip != expected_ip
            mask_mismatch = bool(expected_mask and actual_mask and actual_mask != expected_mask)

            if ip_mismatch or mask_mismatch:
                actual_str = f"{actual_ip or 'sin IP'}" + (f" / {actual_mask}" if actual_mask else "")
                expected_str = f"{expected_ip}" + (f" / {expected_mask}" if expected_mask else "")
                if dev.type in (DeviceType.ROUTER, DeviceType.SWITCH):
                    target_if_name = iface.name if iface else if_label
                    sol = (
                        f"Configura la IP solicitada por la tabla de la actividad en {dev.name}:\n\n"
                        f"{dev.name}# configure terminal\n"
                        f"{dev.name}(config)# interface {target_if_name}\n"
                        f"{dev.name}(config-if)# ip address {expected_ip} {expected_mask or '255.255.255.0'}\n"
                        f"{dev.name}(config-if)# no shutdown"
                    )
                else:
                    sol = (
                        f"Según la tabla de direccionamiento de la actividad, configura en {dev.name} (Desktop → IP Configuration):\n"
                        f"- IP Address: {expected_ip}\n"
                        + (f"- Subnet Mask: {expected_mask}\n" if expected_mask else "")
                        + (f"- Default Gateway: {expected_gw}" if expected_gw else "")
                    )

                findings.append(
                    DiagnosticFinding(
                        id=f"pka_ip_mismatch_{dev.id}_{pair_key[1].replace('/', '_')}",
                        rule_id="RULE_PKA_EXPECTED_IP_MISMATCH",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=dev.id,
                        device_name=dev.name,
                        interface_name=iface.name if iface else if_label,
                        title=f"IP/Máscara en {dev.name} ({if_label}) no coincide con las instrucciones .PKA",
                        description=(
                            f"La tabla de direccionamiento de la práctica exige {expected_str} en {dev.name} ({if_label}), "
                            f"pero actualmente tiene configurado: {actual_str}."
                        ),
                        hint_level1=f"Compara el direccionamiento configurado en {dev.name} con la tabla de direccionamiento del cuadro de instrucciones.",
                        hint_level2=f"Revisa la interfaz {iface.name if iface else if_label} de {dev.name}: la IP o la máscara no coinciden con la actividad.",
                        technical_solution=sol,
                    )
                )

        # Caso C: La tabla exige un Default Gateway específico para un Host/Switch
        if expected_gw and dev.type in (DeviceType.PC, DeviceType.SERVER, DeviceType.SWITCH):
            if dev.default_gateway != expected_gw:
                actual_gw = dev.default_gateway or "sin configurar"
                if dev.type == DeviceType.SWITCH:
                    sol = (
                        f"{dev.name}# configure terminal\n"
                        f"{dev.name}(config)# ip default-gateway {expected_gw}"
                    )
                else:
                    sol = f"En {dev.name} → Desktop → IP Configuration, asigna Default Gateway: {expected_gw}"

                findings.append(
                    DiagnosticFinding(
                        id=f"pka_gw_mismatch_{dev.id}",
                        rule_id="RULE_PKA_EXPECTED_GATEWAY_MISMATCH",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=dev.id,
                        device_name=dev.name,
                        title=f"Default Gateway de {dev.name} no coincide con las instrucciones .PKA",
                        description=(
                            f"La actividad especifica el Default Gateway {expected_gw} para {dev.name}, "
                            f"pero actualmente tiene: {actual_gw}."
                        ),
                        hint_level1=f"¿Qué dirección de puerta de enlace indica la tabla de direccionamiento para {dev.name}?",
                        hint_level2=f"Revisa el Default Gateway en {dev.name}; no coincide con el valor pedido por las instrucciones.",
                        technical_solution=sol,
                    )
                )

    # 2. Complemento por texto: si las instrucciones piden DHCP para las PCs (aunque no hubiera tabla HTML)
    if _text_requests_dhcp_for_hosts(full_text):
        for dev in topology.devices:
            if dev.type != DeviceType.PC or dev.id in checked_dhcp_devices:
                continue
            main_if = dev.interfaces[0] if dev.interfaces else None
            has_dhcp = bool(main_if and main_if.dhcp_enabled)
            has_ip = bool(main_if and main_if.ip_address and main_if.ip_address != "unassigned")
            if not has_dhcp and not has_ip:
                checked_dhcp_devices.add(dev.id)
                findings.append(
                    DiagnosticFinding(
                        id=f"pka_text_dhcp_req_{dev.id}",
                        rule_id="RULE_PKA_HOST_DHCP_REQUIRED",
                        severity=DiagnosticSeverity.ERROR,
                        layer="L3",
                        device_id=dev.id,
                        device_name=dev.name,
                        interface_name=main_if.name if main_if else None,
                        title=f"{dev.name} no tiene IP en modo DHCP (requerido por la actividad .PKA)",
                        description=(
                            f"Las instrucciones de esta práctica indican que las PCs deben obtener su direccionamiento "
                            f"mediante DHCP, pero {dev.name} está en modo Estático y sin dirección IP."
                        ),
                        hint_level1=f"Lee el cuadro de instrucciones de la actividad: ¿las PCs deben recibir su IP de forma manual o automática?",
                        hint_level2=f"En {dev.name}, abre Desktop → IP Configuration y verifica si está seleccionado el modo DHCP.",
                        technical_solution=(
                            f"Según las instrucciones de la práctica (.PKA), activa DHCP en {dev.name}:\n"
                            f"1. Abre {dev.name} → Desktop → IP Configuration.\n"
                            f"2. Selecciona 'DHCP' en lugar de 'Static' para que obtenga su IP automáticamente."
                        ),
                    )
                )

    # 3. Verificar si las instrucciones piden configurar OSPF y ningún router tiene OSPF
    if re.search(r"\b(?:configure|configurar|habilitar|enable|implementar)\b[^.\n]{0,60}\bospf\b", full_text, re.IGNORECASE):
        routers = [d for d in topology.devices if d.type == DeviceType.ROUTER]
        if routers:
            any_ospf = any(
                (r.raw_config and re.search(r"router\s+ospf\s+\d+", r.raw_config, re.IGNORECASE))
                for r in routers
            )
            if not any_ospf:
                sample_r = routers[0]
                findings.append(
                    DiagnosticFinding(
                        id="pka_ospf_missing",
                        rule_id="RULE_PKA_OSPF_REQUIRED",
                        severity=DiagnosticSeverity.WARNING,
                        layer="L3",
                        device_id=sample_r.id,
                        device_name=sample_r.name,
                        title="Enrutamiento OSPF requerido por las instrucciones .PKA no detectado",
                        description=(
                            "Las instrucciones de la actividad solicitan configurar OSPF, pero ningún router "
                            "de la topología tiene un proceso 'router ospf' configurado actualmente."
                        ),
                        hint_level1="¿Qué protocolo de enrutamiento dinámico solicitan configurar las instrucciones de la actividad?",
                        hint_level2=f"Revisa la configuración de los routers (ej. {sample_r.name}); falta declarar el proceso OSPF y anunciar sus redes.",
                        technical_solution=(
                            f"Configura el proceso OSPF en los routers según los parámetros de las instrucciones:\n\n"
                            f"{sample_r.name}(config)# router ospf 1\n"
                            f"{sample_r.name}(config-router)# network <RED> <WILDCARD> area 0"
                        ),
                    )
                )

    return findings
