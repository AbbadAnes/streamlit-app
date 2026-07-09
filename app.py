import streamlit as st
import csv
import io
import json
import os
from datetime import datetime

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

# ---------- Pseudo ----------
if "pseudo" not in st.session_state:
    st.session_state.pseudo = ""

# ---------- En-tête ----------
st.title("🗳️ Vote par élimination")

steps = ["📝 1. On propose des idées", "🗳️ 2. On vote (élimination des 5 dernières)"]
current_step = 0 if data["phase"] == "soumission" else 1
st.progress((current_step + 1) / 2, text=steps[current_step])

with st.expander("ℹ️ Comment ça marche ?"):
    st.markdown("""
    1. **Tout le monde propose des idées** (autant qu'on veut).
    2. Quand toutes les idées sont là, on **lance le vote**.
    3. Chacun **vote pour ses options préférées**.
    4. Un animateur **clôture le tour** : les 5 options avec le moins de votes sont éliminées.
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
        for o in data["options"]:
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"**{o['texte']}**  \n:gray[proposé par {o.get('auteur', '?')}]")
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

    if len(data["options"]) == 1:
        st.balloons()
        st.success(f"## 🏆 Gagnant : **{data['options'][0]['texte']}**")
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
            n_a_eliminer = min(5, n_options - 1)
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
