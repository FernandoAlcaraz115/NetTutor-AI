from typing import List
from app.core.models import Topology, DiagnosticFinding, DiagnosticReport, DiagnosticSeverity
from app.engine.rules.vlan_trunk_rules import check_vlan_trunk_rules
from app.engine.rules.ip_subnet_rules import check_ip_subnet_rules
from app.engine.rules.gateway_rules import check_gateway_rules
from app.engine.rules.interface_status_rules import check_interface_status_rules

class NetworkRuleEngine:
    """
    Motor determinista de análisis y diagnóstico de red.
    Ejecuta heurísticas técnicas de Capa 1, Capa 2 y Capa 3 sobre la topología.
    """

    def __init__(self):
        self.rules = [
            check_interface_status_rules,
            check_vlan_trunk_rules,
            check_ip_subnet_rules,
            check_gateway_rules,
        ]

    def analyze(self, topology: Topology) -> DiagnosticReport:
        all_findings: List[DiagnosticFinding] = []

        for rule_fn in self.rules:
            try:
                findings = rule_fn(topology)
                all_findings.extend(findings)
            except Exception as e:
                print(f"[RuleEngine Error] in {rule_fn.__name__}: {e}")

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
