from typing import List
from app.core.models import Topology, DiagnosticFinding, DiagnosticReport, DiagnosticSeverity
from app.engine.rules.vlan_trunk_rules import check_vlan_trunk_rules
from app.engine.rules.ip_subnet_rules import check_ip_subnet_rules
from app.engine.rules.gateway_rules import check_gateway_rules
from app.engine.rules.interface_status_rules import check_interface_status_rules
from app.engine.rules.static_routing_rules import check_static_routing_rules
from app.engine.rules.ospf_dhcp_rules import check_ospf_dhcp_rules
from app.engine.rules.pka_activity_rules import check_pka_activity_rules

class NetworkRuleEngine:
    """
    Motor determinista de análisis y diagnóstico de red.
    Ejecuta heurísticas técnicas de Capa 1, Capa 2, Capa 3 y requisitos de actividades .PKA.
    """

    def __init__(self):
        self.rules = [
            check_pka_activity_rules,
            check_interface_status_rules,
            check_vlan_trunk_rules,
            check_ip_subnet_rules,
            check_gateway_rules,
            check_static_routing_rules,
            check_ospf_dhcp_rules,
        ]

    def analyze(self, topology: Topology) -> DiagnosticReport:
        all_findings: List[DiagnosticFinding] = []

        for rule_fn in self.rules:
            try:
                findings = rule_fn(topology)
                all_findings.extend(findings)
            except Exception as e:
                print(f"[RuleEngine Error] in {rule_fn.__name__}: {e}")

        # Si hay hallazgos específicos basados en instrucciones .PKA para un dispositivo
        # (ej. falta DHCP o IP/Gateway de la tabla), suprimir el hallazgo genérico redundante
        pka_ip_devices = {
            f.device_id
            for f in all_findings
            if f.rule_id in (
                "RULE_PKA_HOST_DHCP_REQUIRED",
                "RULE_PKA_HOST_DHCP_NO_LEASE",
                "RULE_PKA_EXPECTED_IP_MISMATCH",
            )
        }
        pka_gw_devices = {
            f.device_id
            for f in all_findings
            if f.rule_id in (
                "RULE_PKA_HOST_DHCP_REQUIRED",
                "RULE_PKA_HOST_DHCP_NO_LEASE",
                "RULE_PKA_EXPECTED_GATEWAY_MISMATCH",
            )
        }
        all_findings = [
            f
            for f in all_findings
            if not (
                (f.rule_id == "RULE_L3_HOST_UNCONFIGURED_IP" and f.device_id in pka_ip_devices)
                or (f.rule_id == "RULE_L3_MISSING_DEFAULT_GATEWAY" and f.device_id in pka_gw_devices)
            )
        ]

        # Contadores de severidad
        errors = sum(1 for f in all_findings if f.severity == DiagnosticSeverity.ERROR)
        warnings = sum(1 for f in all_findings if f.severity == DiagnosticSeverity.WARNING)

        # Cálculo de puntaje pedagógico (base 100%, penaliza errores con -20% y warnings con -5%)
        penalty = (errors * 20.0) + (warnings * 5.0)
        score = max(0.0, 100.0 - penalty)

        return DiagnosticReport(
            topology_id=topology.id,
            total_issues=len(all_findings),
            errors_count=errors,
            warnings_count=warnings,
            score_percentage=round(score, 1),
            findings=all_findings
        )

# Instancia singleton del motor
rule_engine = NetworkRuleEngine()
