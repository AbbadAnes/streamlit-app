import streamlit as st
import json
import os
from datetime import datetime

DATA_FILE = "data.json"

st.set_page_config(page_title="Vote par élimination", page_icon="🗳️", layout="centered")

# ---------- Stockage partagé (fichier JSON, partagé entre tous les visiteurs) ----------

def load_data():
    if not os.path.exists(DATA_FILE):
        default = {
            "phase": "soumission",   # "soumission" ou "vote"
            "round": 1,
            "options": [],           # [{"id": str, "texte": str, "votes": int}]
            "eliminated_last_round": [],
            "voters": {}             # {"round-pseudo": [option_id, ...]} pour éviter les doublons
        }
        save_data(default)
        return default
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

data = load_data()

st.title("🗳️ Vote par élimination")
st.caption(f"Round {data['round']} — Phase : {'📝 Soumission des idées' if data['phase'] == 'soumission' else '🗳️ Vote en cours'}")

# ---------- Pseudo (simple, pas d'authentification réelle) ----------
if "pseudo" not in st.session_state:
    st.session_state.pseudo = ""

st.session_state.pseudo = st.text_input("Ton pseudo (pour éviter de voter plusieurs fois)", value=st.session_state.pseudo)
pseudo = st.session_state.pseudo.strip()

st.divider()

# ---------- PHASE 1 : SOUMISSION ----------
if data["phase"] == "soumission":
    st.subheader("Propose une option")
    with st.form("ajout_option", clear_on_submit=True):
        texte = st.text_input("Ton idée")
        submitted = st.form_submit_button("Ajouter")
        if submitted and texte.strip():
            data["options"].append({
                "id": f"{datetime.now().timestamp()}",
                "texte": texte.strip(),
                "votes": 0
            })
            save_data(data)
            st.success("Ajouté !")
            st.rerun()

    st.subheader(f"Options proposées ({len(data['options'])})")
    for o in data["options"]:
        st.write(f"• {o['texte']}")

    st.divider()
    if len(data["options"]) >= 2:
        if st.button("▶️ Passer au vote (verrouille les propositions)", type="primary"):
            data["phase"] = "vote"
            save_data(data)
            st.rerun()
    else:
        st.info("Il faut au moins 2 options pour lancer le vote.")

# ---------- PHASE 2 : VOTE ----------
else:
    st.subheader(f"Vote — Round {data['round']}")

    if data["eliminated_last_round"]:
        st.warning("Éliminés au tour précédent : " + ", ".join(data["eliminated_last_round"]))

    if not pseudo:
        st.info("Entre un pseudo ci-dessus pour pouvoir voter.")
    else:
        vote_key = f"{data['round']}-{pseudo}"
        deja_vote = vote_key in data["voters"]

        options_triees = sorted(data["options"], key=lambda o: -o["votes"])

        for o in options_triees:
            c1, c2, c3 = st.columns([3, 1, 1])
            c1.write(f"**{o['texte']}**")
            c2.write(f"{o['votes']} vote(s)")
            if not deja_vote:
                if c3.button("Voter", key=f"vote_{o['id']}"):
                    o["votes"] += 1
                    data["voters"][vote_key] = o["id"]
                    save_data(data)
                    st.rerun()
            else:
                voted_id = data["voters"][vote_key]
                if voted_id == o["id"]:
                    c3.write("✅ ton choix")

        if deja_vote:
            st.info("Tu as déjà voté ce tour-ci. Attends le tour suivant.")

    st.divider()
    st.caption("Un administrateur peut clôturer le tour ci-dessous (élimine les 5 derniers).")

    if st.button("⏭️ Clôturer le tour et éliminer les 5 derniers"):
        options_triees = sorted(data["options"], key=lambda o: o["votes"])
        n_options = len(options_triees)

        if n_options <= 1:
            st.error("Il ne reste qu'une seule option, impossible d'éliminer davantage.")
        else:
            n_a_eliminer = min(5, n_options - 1)  # garder au moins 1 option
            elimines = options_triees[:n_a_eliminer]
            restants = options_triees[n_a_eliminer:]

            for o in restants:
                o["votes"] = 0

            data["options"] = restants
            data["eliminated_last_round"] = [o["texte"] for o in elimines]
            data["round"] += 1
            data["voters"] = {}
            save_data(data)
            st.rerun()

    if len(data["options"]) == 1:
        st.balloons()
        st.success(f"🏆 Gagnant : **{data['options'][0]['texte']}**")

    st.divider()
    if st.button("🔄 Réinitialiser tout (nouvelle session)"):
        os.remove(DATA_FILE) if os.path.exists(DATA_FILE) else None
        st.rerun()
