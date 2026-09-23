import streamlit as st

from iel_hackathon.chat import render_chat

st.set_page_config(page_title="IEL Hackathon")

st.title("IEL Hackathon")
st.write("Conteúdo da página. Use o botão no canto inferior direito para abrir o chat.")

render_chat()
