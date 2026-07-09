import streamlit as st
import csv
import io
import json
import os
import re
import socket
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import requests

DATA_FILE = "data.json"

st.set_page_config(page_title="Vote par élimination", page_icon="🗳️", layout="centered")

# ---------- Stockage partagé (fichier JSON, partagé entre tous les visiteurs) ----------

DEFAULT_DATA = {
    "phase": "soumission",
    "round": 1,
    "options": [],
    "eliminated_history": [],   # liste de listes, une par round
    "voters": {}
}

def load_data():
    if not os.path.exists(DATA_FILE):
        default = json.loads(json.dumps(DEFAULT_DATA))
        save_data(default)
        return default
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Un data.json créé par une ancienne version peut ne pas avoir toutes les clés
    missing = [k for k in DEFAULT_DATA if k not in data]
    for k in missing:
        data[k] = json.loads(json.dumps(DEFAULT_DATA[k]))
    # État incohérent (ex. vieux fichier) : en phase vote sans options, on repart en soumission
    if data["phase"] != "soumission" and not data["options"]:
        data["phase"] = "soumission"
        missing.append("phase")
    if missing:
        save_data(data)
    return data

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

# ---------- Disponibilité des noms de domaine ----------

TLDS = [".io", ".ai", ".com", ".fr"]

def domain_base(texte):
    """Transforme une idée en nom de domaine : accents et espaces retirés, minuscules."""
    s = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9-]", "", s.lower().replace(" ", ""))

# RDAP des registres officiels, interrogés en direct (rdap.org, mutualisé, rate-limite vite)
RDAP_ENDPOINTS = {
    ".com": "https://rdap.verisign.com/com/v1/domain/{}",
    ".io": "https://rdap.identitydigital.services/rdap/domain/{}",
    ".ai": "https://rdap.identitydigital.services/rdap/domain/{}",
    ".fr": "https://rdap.nic.fr/domain/{}",
}

def rdap_check(domaine):
    tld = "." + domaine.rsplit(".", 1)[1]
    urls = [RDAP_ENDPOINTS[tld].format(domaine)] if tld in RDAP_ENDPOINTS else []
    urls.append(f"https://rdap.org/domain/{domaine}")
    for url in urls:
        for _ in range(2):  # une relance en cas de rate-limit
            try:
                r = requests.get(url, timeout=6)
            except requests.RequestException:
                break
            if r.status_code == 404:
                return True
            if r.status_code == 200:
                return False
            if r.status_code == 429:
                time.sleep(1)
                continue
            break
    return None

def dns_check(domaine):
    """DNS-over-HTTPS Cloudflare : NXDOMAIN = très probablement libre, réponse NS = pris."""
    try:
        r = requests.get(
            "https://cloudflare-dns.com/dns-query",
            params={"name": domaine, "type": "NS"},
            headers={"accept": "application/dns-json"},
            timeout=6,
        )
        reponse = r.json()
        if reponse.get("Status") == 3:      # NXDOMAIN
            return True
        if reponse.get("Status") == 0 and reponse.get("Answer"):
            return False
    except (requests.RequestException, ValueError):
        pass
    # Dernier recours : résolution locale — s'il résout, il est forcément pris
    try:
        socket.getaddrinfo(domaine, None)
        return False
    except socket.gaierror:
        return None

def check_domaine(domaine):
    """True = libre, False = pris, None = indéterminé."""
    resultat = rdap_check(domaine)
    if resultat is None:
        resultat = dns_check(domaine)
    return resultat

@st.cache_resource
def _domain_cache():
    # Partagé entre tous les visiteurs et tous les reruns
    return {}

def verifier_domaines(options):
    """Vérifie base+TLD pour chaque option, en parallèle, avec cache global."""
    domaines = []
    for o in options:
        base = domain_base(o["texte"])
        if base:
            domaines.extend(base + tld for tld in TLDS)
    cache = _domain_cache()
    manquants = [d for d in domaines if d not in cache]
    if manquants:
        with st.spinner(f"🌐 Vérification de {len(manquants)} domaine(s)..."):
            with ThreadPoolExecutor(max_workers=8) as ex:
                for d, res in zip(manquants, ex.map(check_domaine, manquants)):
                    if res is not None:  # ne pas figer les échecs : on retentera au prochain chargement
                        cache[d] = res
    return cache

def ligne_domaines(texte, cache):
    base = domain_base(texte)
    if not base:
        return None
    parts = []
    for tld in TLDS:
        d = base + tld
        dispo = cache.get(d)
        if dispo is True:
            parts.append(f":green[**{d}** ✔]")
        elif dispo is False:
            parts.append(f"❌ [{d}](http://{d})")
        else:
            parts.append(f":gray[{d} ?]")
    return " · ".join(parts)

# ---------- Pseudo ----------
if "pseudo" not in st.session_state:
    st.session_state.pseudo = ""

# ---------- En-tête ----------
st.title("🗳️ Vote par élimination")

steps = ["📝 1. On propose des idées", "🗳️ 2. On vote (élimination à chaque tour)"]
current_step = 0 if data["phase"] == "soumission" else 1
st.progress((current_step + 1) / 2, text=steps[current_step])

with st.expander("ℹ️ Comment ça marche ?"):
    st.markdown("""
    1. **Tout le monde propose des idées** (autant qu'on veut).
    2. Quand toutes les idées sont là, on **lance le vote**.
    3. Chacun **vote pour ses options préférées**.
    4. Un animateur **clôture le tour** en choisissant **combien d'options éliminer** : celles avec le moins de votes sont éliminées.
    5. On revote sur les options restantes, jusqu'à ce qu'il n'en reste qu'une : le gagnant 🏆
    """)

st.divider()

# ---------- Pseudo, requis dès le début ----------
pseudo = st.text_input(
    "👤 Ton prénom ou pseudo",
    value=st.session_state.pseudo,
    placeholder="Ex : Anes",
    help="Sert juste à éviter que tu votes plusieurs fois. Pas besoin de compte."
)
st.session_state.pseudo = pseudo
pseudo = pseudo.strip()

if not pseudo:
    st.info("⬆️ Commence par entrer ton prénom pour continuer.")
    st.stop()

st.divider()

# ================= PHASE 1 : SOUMISSION =================
if data["phase"] == "soumission":

    st.subheader("✏️ Propose ton idée")
    with st.form("ajout_option", clear_on_submit=True, border=True):
        texte = st.text_input("Ton idée", label_visibility="collapsed", placeholder="Écris ton idée ici...")
        submitted = st.form_submit_button("➕ Ajouter cette idée", type="primary", use_container_width=True)
        if submitted:
            if texte.strip():
                data["options"].append({
                    "id": f"{datetime.now().timestamp()}",
                    "texte": texte.strip(),
                    "auteur": pseudo,
                    "votes": 0
                })
                save_data(data)
                st.rerun()
            else:
                st.warning("Écris quelque chose avant d'ajouter.")

    st.subheader(f"💡 Idées proposées ({len(data['options'])})")

    if not data["options"]:
        st.caption("Aucune idée pour l'instant. Sois le premier à en proposer une !")
    else:
        domaines = verifier_domaines(data["options"])
        for o in data["options"]:
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"**{o['texte']}**  \n:gray[proposé par {o.get('auteur', '?')}]")
                ligne = ligne_domaines(o["texte"], domaines)
                if ligne:
                    st.caption(ligne)
            with c2:
                if o.get("auteur") == pseudo:
                    if st.button("🗑️", key=f"del_{o['id']}", help="Supprimer ta proposition"):
                        data["options"] = [x for x in data["options"] if x["id"] != o["id"]]
                        save_data(data)
                        st.rerun()
            st.divider()

    st.subheader("🚀 Prêt à voter ?")
    if len(data["options"]) >= 2:
        st.button(
            f"▶️ Lancer le vote sur les {len(data['options'])} idées",
            type="primary",
            use_container_width=True,
            on_click=lambda: (data.update({"phase": "vote"}), save_data(data))
        )
        st.caption("⚠️ Une fois lancé, plus personne ne pourra ajouter d'idée.")
    else:
        st.info("Il faut au moins 2 idées pour lancer le vote.")

# ================= PHASE 2 : VOTE =================
else:
    st.subheader(f"🗳️ Round {data['round']} — à toi de voter")

    if data["eliminated_history"]:
        with st.expander(f"☠️ Voir les {sum(len(r) for r in data['eliminated_history'])} idées déjà éliminées"):
            for i, elims in enumerate(data["eliminated_history"], start=1):
                st.caption(f"Round {i} : " + ", ".join(elims))

    vote_key = f"{data['round']}-{pseudo}"
    deja_vote_id = data["voters"].get(vote_key)

    domaines = verifier_domaines(data["options"])

    if len(data["options"]) == 1:
        st.balloons()
        st.success(f"## 🏆 Gagnant : **{data['options'][0]['texte']}**")
        ligne = ligne_domaines(data["options"][0]["texte"], domaines)
        if ligne:
            st.markdown(ligne)
    else:
        options_triees = sorted(data["options"], key=lambda o: -o["votes"])
        total_votes = sum(o["votes"] for o in options_triees) or 1
        max_votes = max((o["votes"] for o in options_triees), default=0) or 1

        if deja_vote_id:
            st.success("✅ Ton vote est enregistré pour ce tour. Reviens au prochain round !")

        for o in options_triees:
            with st.container(border=True):
                c1, c2 = st.columns([4, 1])
                with c1:
                    label = f"**{o['texte']}**"
                    if deja_vote_id == o["id"]:
                        label += "  ✅"
                    st.markdown(label)
                    ligne = ligne_domaines(o["texte"], domaines)
                    if ligne:
                        st.caption(ligne)
                    st.progress(o["votes"] / max_votes if max_votes else 0, text=f"{o['votes']} vote(s)")
                with c2:
                    disabled = bool(deja_vote_id)
                    if st.button("👍 Voter", key=f"vote_{o['id']}", disabled=disabled, use_container_width=True):
                        o["votes"] += 1
                        data["voters"][vote_key] = o["id"]
                        save_data(data)
                        st.rerun()

    st.divider()
    with st.expander("🎛️ Espace animateur (clôturer le tour)"):
        st.caption("À utiliser quand tout le monde a voté, pour passer au round suivant.")
        n_options = len(data["options"])
        if n_options <= 1:
            st.caption("Il ne reste qu'une option, il n'y a plus rien à clôturer.")
        else:
            n_a_eliminer = st.number_input(
                "Nombre d'options à éliminer ce tour",
                min_value=1,
                max_value=n_options - 1,
                value=1,
                help="Les options avec le moins de votes seront éliminées. Il restera toujours au moins une option."
            )
            if st.button(f"⏭️ Clôturer le round {data['round']} (élimine {n_a_eliminer} option(s))", type="primary"):
                options_triees = sorted(data["options"], key=lambda o: o["votes"])
                elimines = options_triees[:n_a_eliminer]
                restants = options_triees[n_a_eliminer:]
                for o in restants:
                    o["votes"] = 0
                data["options"] = restants
                data["eliminated_history"].append([o["texte"] for o in elimines])
                data["round"] += 1
                data["voters"] = {}
                save_data(data)
                st.rerun()

        st.divider()
        if st.button("🔄 Tout réinitialiser (nouvelle session complète)"):
            if os.path.exists(DATA_FILE):
                os.remove(DATA_FILE)
            st.rerun()

# ================= EXPORT / IMPORT CSV =================

def options_to_csv(options):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["texte", "auteur", "votes"])
    for o in options:
        writer.writerow([o["texte"], o.get("auteur", ""), o["votes"]])
    # BOM UTF-8 pour qu'Excel ouvre le fichier avec les accents corrects
    return buf.getvalue().encode("utf-8-sig")

def options_from_csv(raw_bytes):
    texte = raw_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(texte))
    if reader.fieldnames is None or "texte" not in reader.fieldnames:
        raise ValueError("Le CSV doit avoir au moins une colonne « texte » (et optionnellement « auteur », « votes »).")
    options = []
    for i, row in enumerate(reader):
        if not (row.get("texte") or "").strip():
            continue
        try:
            votes = int(row.get("votes") or 0)
        except ValueError:
            votes = 0
        options.append({
            "id": f"import-{i}-{datetime.now().timestamp()}",
            "texte": row["texte"].strip(),
            "auteur": (row.get("auteur") or "").strip() or "import",
            "votes": votes
        })
    if not options:
        raise ValueError("Aucune option trouvée dans le CSV.")
    return options

st.divider()
with st.expander("💾 Exporter / importer les votes (CSV)"):
    st.download_button(
        f"⬇️ Exporter les {len(data['options'])} option(s) et leurs votes",
        data=options_to_csv(data["options"]),
        file_name=f"votes-round-{data['round']}.csv",
        mime="text/csv",
        use_container_width=True,
        disabled=not data["options"]
    )

    st.divider()
    fichier = st.file_uploader(
        "Importer un CSV (colonnes : texte, auteur, votes)",
        type=["csv"],
        help="Remplace les options actuelles par celles du fichier. "
             "S'il contient des votes, la session reprend en phase de vote ; sinon en phase de soumission."
    )
    if fichier is not None:
        st.warning("⚠️ L'import remplace toutes les options et votes actuels.")
        if st.button("📥 Importer et remplacer", type="primary", use_container_width=True):
            try:
                options = options_from_csv(fichier.getvalue())
            except (ValueError, UnicodeDecodeError) as e:
                st.error(f"Import impossible : {e}")
            else:
                data["options"] = options
                data["phase"] = "vote" if any(o["votes"] for o in options) else "soumission"
                data["round"] = 1
                data["eliminated_history"] = []
                data["voters"] = {}
                save_data(data)
                st.rerun()
