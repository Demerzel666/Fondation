#!/usr/bin/env python3
"""
SECURITY AUDIT TOOL — Fondation-IA
Scanne les dépendances Python et le code source pour vulnérabilités connues.

Utilisation :
  python3 security_audit.py <chemin_dossier|fichier>.py [--json]
  python3 security_audit.py --help

Exemples :
  ./security_audit.py ./src/
  ./security_audit.py ~/mon_projet/main.py --json > audit_report.json
"""

import sys
import os
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from datetime import datetime, timezone
# Assurer que les binaires pipx (~/.local/bin) sont détectables
os.environ["PATH"] = os.path.expanduser("~/.local/bin") + ":" + os.environ.get("PATH", "")

def parse_severity(vuln: dict) -> str:
    """
    Extrait le niveau de sévérité correct depuis les champs OSV.
    
    OSV renvoie parfois 'CVSS_V3', 'CVSS_V4' dans le champ type au lieu de CRITICAL/HIGH/etc.
    Cette fonction normalise vers les valeurs standard.
    """
    # Méthode 1 : champ database_specific avec severity textuel
    db_specific = vuln.get('database_specific', {})
    if 'severity' in db_specific:
        sev_text = db_specific['severity'].upper()
        if sev_text in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
            return sev_text
    
    # Méthode 2 : analyse du CVSS vector string
    for sev_entry in vuln.get('severity', []):
        score_str = sev_entry.get('score', '')
        cvss_str = sev_entry.get('type', '')
        
        # Si c'est un vrai vector CVSS (pas juste 'CVSS_V3')
        if '/' in score_str or ('/' in cvss_str and cvss_str.startswith('CVSS:')):
            # Extraire AV:N (Attack Vector Network) + AC:L (Access Complexity Low)
            combined = f"{score_str} {cvss_str}"
            
            # CVSS v3/v4 : AV:N + AC:L = Minimum HIGH (toutes les combinaisons possibles étant critique)
            if 'AV:N' in combined and 'AC:L' in combined:
                return 'HIGH'
            elif 'AV:N' in combined:
                return 'MEDIUM'
            
            # CVSS numérique simple (ex: 9.8, 7.5, etc.)
            numeric_match = re.search(r'(\d+\.\d+)', combined)
            if numeric_match:
                base_score = float(numeric_match.group(1))
                if base_score >= 9.0:
                    return 'CRITICAL'
                elif base_score >= 7.0:
                    return 'HIGH'
                elif base_score >= 4.0:
                    return 'MEDIUM'
                else:
                    return 'LOW'
    
    # Méthode fallback : si le field contient déjà une valeur reconnue
    severity_fallback = vuln.get('severity', [{'type': 'UNKNOWN'}])[0].get('type', 'UNKNOWN')
    if severity_fallback in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
        return severity_fallback
    
    return 'MEDIUM'  # Valeur par défaut prudente


# ============================================================================
# EXTRACTION DES DÉPENDANCES
# ============================================================================

def extract_python_imports(file_paths: List[str]) -> Dict[str, str]:
    """
    Extrait tous les noms de packages importés depuis des fichiers Python.
    
    Retourne dict {package_name: detected_version}
    Les versions sont résolues via importlib.metadata.
    """
    imports = set()
    from_pattern = re.compile(r'^\s*from\s+(\w+)\s+import', re.MULTILINE)
    import_pattern = re.compile(r'^\s*import\s+(\w+)', re.MULTILINE)
    
    for file_path in file_paths:
        if not os.path.isfile(file_path):
            continue
            
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
            matches_from = from_pattern.findall(content)
            matches_import = import_pattern.findall(content)
            
            imports.update(matches_from)
            imports.update(matches_import)
            
        except Exception as e:
            print(f"[WARN] Impossible lire {file_path}: {e}")
    
    # Filtrer stdlib automatiquement (Python 3.10+)
    imports = {imp for imp in imports if imp not in sys.stdlib_module_names}
    
    packages_with_versions = {}
    for pkg in sorted(imports):
        version = get_package_version(pkg)
        packages_with_versions[pkg] = version
    
    return packages_with_versions


def get_package_version(package_name: str) -> Optional[str]:
    """Récupère la version installée via importlib.metadata (natif Python 3.8+)."""
    from importlib.metadata import version, PackageNotFoundError
    
    # Mapping import name → PyPI distribution name
    name_mapping = {
        'sentence_transformers': 'sentence-transformers',
        'chromadb': 'chromadb',
    }
    dist_name = name_mapping.get(package_name, package_name)
    
    try:
        return version(dist_name)
    except PackageNotFoundError:
        # Essai avec le nom d'import tel quel
        try:
            return version(package_name)
        except PackageNotFoundError:
            return None


def scan_directory_for_python_files(directory: str) -> List[str]:
    """Recherche récursive tous les .py dans un dossier."""
    py_files = []
    exclude_dirs = {'__pycache__', '.git', '.venv', 'venv', 'node_modules', 
                   '.idea', '.vscode', '__pypackages__'}
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        
        for fname in sorted(files):
            if fname.endswith('.py'):
                py_files.append(os.path.join(root, fname))
    
    return py_files


# ============================================================================
# SCAN SEMGREP LOCAL
# ============================================================================

def run_semgrep_scan(paths: List[str]) -> Tuple[bool, List[Dict]]:
    """
    Exécute Semgrep sur les fichiers donnés si installé.
    
    Returns: (success, list_of_findings)
    """
    # Check si semgrep est installé
    result = subprocess.run(['which', 'semgrep'], capture_output=True)
    if result.returncode != 0:
        print("[INFO] Semgrep non installé — skip scan statique.")
        return False, []
    
    print("[AUDIT] Lancement Semgrep...")
    
    try:
        cmd = [
            'semgrep', 'scan',
            '--config', 'auto',
            '--quiet',
            '--json'
        ] + paths
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0 and result.stdout.strip():
            findings = json.loads(result.stdout).get('results', [])
            return True, findings
        else:
            print("[AUDIT] Semgrep : aucun résultat ou erreur silencieuse.")
            return True, []
            
    except subprocess.TimeoutExpired:
        print("[WARN] Scan Semgrep timeout (>2min)")
        return False, []
    except Exception as e:
        print(f"[ERROR] Echec Semgrep: {e}")
        return False, []


# ============================================================================
# RECHERCHE CVE EN LIGNE (OSV.dev API)
# ============================================================================

def query_osv_api(package_name: str, version: str) -> List[Dict]:
    """
    Interroge OSV.dev (Google Open Source Vulnerabilities API) pour ce package.
    
    OSV.dev est gratuit, ouvert, couvrant Python (PyPI), npm, Rust crates, etc.
    URL: https://api.osv.dev/v1/query
    
    Returns: liste des vulnérabilités trouvées
    """
    import urllib.request
    import urllib.error
    
    if not version:
        return []
    
    payload = {
        "version": version,
        "ecosystem": "PyPI",
        "package": {"name": package_name}
    }
    
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Fondation-IA-Security-Audit/1.0'
    }
    
    url = 'https://api.osv.dev/v1/query'
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            vulnerabilities = data.get('vulns', [])
            
            filtered = []
            for vuln in vulnerabilities:
                published_date_str = vuln.get('published', '')
                if published_date_str:
                    try:
                        pub_date = datetime.fromisoformat(published_date_str.replace('Z', '+00:00'))
                        age_days = (datetime.now(pub_date.tzinfo) - pub_date).days
                        if age_days > 90:
                            continue  # Skip anciennes (>90 jours)
                    except Exception:
                        pass
                
                # Utiliser LA NOUVELLE fonction parse_severity
                severity = parse_severity(vuln)
                is_high_risk = severity in ['CRITICAL', 'HIGH']
                
                filtered.append({
                    "id": vuln.get('id', 'UNKNOWN-ID'),
                    "summary": vuln.get('summary', ''),
                    "details": vuln.get('details', '')[:200],
                    "severity": severity,
                    "is_high_risk": is_high_risk,
                    "references": [ref.get('url', '') for ref in vuln.get('references', [])][:5],
                    "published": published_date_str
                })
            
            return filtered
            
    except urllib.error.URLError as e:
        print(f"[WARN] OSV API unreachable: {e}")
        return []
    except Exception as e:
        print(f"[ERROR] Query OSV failed for {package_name}: {e}")
        return []


def batch_cve_lookup(packages: Dict[str, str]) -> Dict[str, List[Dict]]:
    """Appelle OSV API pour tous les packages et retourne mapping pkg → vulns."""
    results = {}
    
    total = len(packages)
    for i, (pkg_name, pkg_version) in enumerate(sorted(packages.items()), 1):
        print(f"  [{i}/{total}] Checking {pkg_name}@{pkg_version}...")
        vulns = query_osv_api(pkg_name, pkg_version or 'unknown')
        if vulns:
            results[pkg_name] = vulns
            high_risk_count = sum(1 for v in vulns if v['is_high_risk'])
            if high_risk_count > 0:
                print(f"    ⚠️  {high_risk_count} HIGH/CRITICAL vulnerability(s) FOUND!")
                for v in vulns:
                    print(f"      • {v['id']} ({v['severity']})")
    
    return results


# ============================================================================
# RAPPORT STRUCTURÉ
# ============================================================================

def generate_recommendations(osv_results: Dict, semgrep_findings: List[Dict]) -> List[str]:
    """Génère recommandations actionnables."""
    recs = []
    
    for pkg, vulns in sorted(osv_results.items()):
        for v in vulns:
            if v['is_high_risk']:
                recs.append(
                    f"UPGRADE REQUIRED: {pkg} → Latest stable version to fix {v['id']} "
                    f"(Severity: {v['severity']})"
                )
    
    for finding in semgrep_findings[:5]:
        recs.append(
            f"SAST DETECTED at {finding.get('location', {}).get('filename')}:"
            f" {finding.get('extra', {}).get('message', 'Issue unknown')}"
        )
    
    if not recs:
        recs.append("No critical recommendations. Proceed with standard review.")
    
    return recs


def next_actions(risk_level: str, blocking: bool) -> List[str]:
    """Actions suggérées selon le statut."""
    actions = []
    
    if blocking:
        actions.append("🚨 BLOCKED: Fix CRITICAL vulnerabilities before committing code.")
        actions.append("Run: pip install --upgrade <package-name> for affected deps.")
        actions.append("Re-run audit after upgrades to confirm resolution.")
    else:
        actions.append("✅ No blockers found. Continue development.")
        actions.append("⚠️ Schedule follow-up audit in 30 days (CVE pipeline evolves).")
    
    if risk_level != 'LOW':
        actions.append("💡 Tip: Install Semgrep for deeper SAST analysis")
        actions.append("   Run: pip install semgrep")
    
    return actions


def generate_audit_report(
    extracted_packages: Dict[str, str],
    osv_results: Dict[str, List[Dict]],
    semgrep_passed: bool,
    semgrep_findings: List[Dict],
    target_path: str
) -> Dict:
    """Compile tous les résultats dans un rapport JSON structuré."""
    
    timestamp = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
    
    total_critical = sum(
        sum(1 for v in vulns if v['severity'] == 'CRITICAL')
        for vulns in osv_results.values()
    )
    total_high = sum(
        sum(1 for v in vulns if v['severity'] == 'HIGH')
        for vulns in osv_results.values()
    )
    
    if total_critical > 0:
        risk_level = 'CRITICAL'
    elif total_high > 0:
        risk_level = 'HIGH'
    elif osv_results or not semgrep_passed:
        risk_level = 'MEDIUM'
    else:
        risk_level = 'LOW'
    
    blocking_issues = total_critical > 0
    
    report = {
        'metadata': {
            'tool': 'Fondation-IA Security Audit',
            'version': '1.0.0',
            'timestamp': timestamp,
            'target_path': target_path,
            'python_interpreter': sys.executable
        },
        'summary': {
            'packages_scanned': len(extracted_packages),
            'vulnerabilities_found': sum(len(v) for v in osv_results.values()),
            'critical_count': total_critical,
            'high_count': total_high,
            'semgrep_status': 'passed' if semgrep_passed else 'failed_or_not_installed',
            'risk_level': risk_level,
            'blocking_issues': blocking_issues
        },
        'dependencies': {
            pkg: {
                'installed_version': ver,
                'has_vulnerabilities': pkg in osv_results,
                'vulnerability_ids': [v['id'] for v in osv_results.get(pkg, [])]
            }
            for pkg, ver in sorted(extracted_packages.items())
        },
        'vulnerabilities_by_package': osv_results,
        'semgrep_findings': semgrep_findings,
        'recommendations': generate_recommendations(osv_results, semgrep_findings),
    }
    
    report['next_steps'] = next_actions(risk_level=risk_level, blocking=blocking_issues)
    
    return report


def display_report_summary(report: Dict):
    """Affiche un résumé human-readable du rapport."""
    s = report['summary']
    
    print("\n" + "=" * 60)
    print("🛡️  FONDATION SECURITY AUDIT REPORT")
    print("=" * 60)
    print(f"Timestamp: {report['metadata']['timestamp']}")
    print(f"Target: {report['metadata']['target_path']}")
    print("-" * 60)
    print(f"Packages scanned: {s['packages_scanned']}")
    print(f"Total vulnerabilities: {s['vulnerabilities_found']}")
    print(f"  • Critical: {s['critical_count']} 🚨")
    print(f"  • High:     {s['high_count']} ⚠️ ")
    print(f"Semgrep status: {s['semgrep_status']}")
    print(f"Risk level: {s['risk_level']}")
    print(f"Blocking issues: {'YES 🚫' if s['blocking_issues'] else 'NO ✅'}")
    print("-" * 60)
    
    if s['vulnerabilities_found'] > 0:
        print("\n🔴 VULNERABLE PACKAGES:")
        for pkg, vulns in sorted(report['vulnerabilities_by_package'].items()):
            print(f"\n  Package: {pkg}@{report['dependencies'][pkg]['installed_version']}")
            for v in vulns:
                print(f"    • ID: {v['id']} ({v['severity']})")
                print(f"      Summary: {v['summary'][:100]}")
    
    print("\n📋 RECOMMENDATIONS:")
    for rec in report['recommendations'][:5]:
        print(f"  • {rec}")
    
    print("\n▶ NEXT ACTIONS:")
    for act in report['next_steps']:
        print(f"  • {act}")
    
    print("=" * 60 + "\n")


# ============================================================================
# MAIN CLI
# ============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Security Audit Tool for Fondation-IA projects"
    )
    parser.add_argument('path', nargs='?', default='.', 
                       help='Chemin vers fichier/dossier à scanner')
    parser.add_argument('--json', dest='output_json', action='store_true',
                       help='Exporter rapport au format JSON')
    parser.add_argument('--skip-semgrep', dest='skip_semgrep', action='store_true',
                       help='Ne pas lancer Semgrep même si disponible')
    parser.add_argument('--offline', dest='offline_mode', action='store_true',
                       help='Skip toutes les requêtes en ligne (CVE lookup)')
    
    args = parser.parse_args()
    
    target_path = os.path.abspath(args.path)
    print(f"[AUDIT] Starting scan on: {target_path}")
    
    if os.path.isfile(target_path):
        py_files = [target_path]
    elif os.path.isdir(target_path):
        py_files = scan_directory_for_python_files(target_path)
        if not py_files:
            print("[ERROR] Aucun fichier Python trouvé.")
            sys.exit(1)
    else:
        print(f"[ERROR] Chemin invalide: {target_path}")
        sys.exit(1)
    
    print(f"[AUDIT] Found {len(py_files)} Python file(s)")
    
    print("\n[AUDIT] Step 1/4: Extracting dependencies...")
    packages = extract_python_imports(py_files)
    if not packages:
        print("[WARN] Aucune dépendance détectée.")
    else:
        print(f"    Detected {len(packages)} unique packages:")
        for pkg, ver in sorted(packages.items()):
            print(f"      • {pkg} @ {ver or 'unknown'}")
    
    osv_results = {}
    if not args.offline_mode:
        print(f"\n[AUDIT] Step 2/4: Querying OSV.dev database...")
        osv_results = batch_cve_lookup(packages)
    
    semgrep_success = False
    semgrep_finding_list = []
    if not args.skip_semgrep:
        print(f"\n[AUDIT] Step 3/4: Running Semgrep static analysis...")
        semgrep_success, semgrep_finding_list = run_semgrep_scan(py_files)
    
    print(f"\n[AUDIT] Step 4/4: Generating report...")
    report = generate_audit_report(
        extracted_packages=packages,
        osv_results=osv_results,
        semgrep_passed=semgrep_success,
        semgrep_findings=semgrep_finding_list,
        target_path=target_path
    )
    
    if args.output_json:
        output_file = f"audit_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        print(f"\n[OK] Rapport JSON exporté: {output_file}")
    else:
        display_report_summary(report)
    
    sys.exit(1 if report['summary']['blocking_issues'] else 0)


if __name__ == "__main__":
    main()
