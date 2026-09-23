import streamlit as st

from iel_hackathon.chat import render_chat
from iel_hackathon.sidebar import render_sidebar

# "locked": a barra lateral do design não recolhe.
st.set_page_config(page_title="IEL Hackathon", initial_sidebar_state="locked")

render_sidebar()

st.title("IEL Hackathon")
st.write("Conteúdo da página. Use o botão no canto inferior direito para abrir o chat.")

render_chat()
