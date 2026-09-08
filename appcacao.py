import psycopg2
from psycopg2.extras import RealDictCursor   # si vous voulez des dictionnaires pour les résultats
import os
import io
import hashlib
import streamlit as st
import pandas as pd
from fpdf import FPDF
import sys
import re
import base64
import tempfile
import logging
from reportlab.lib.utils import ImageReader
from num2words import num2words
from datetime import datetime, date, timedelta  # 👈 Très important pour la gestion des dates et délais !
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Configuration du logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(page_title="ERP FRIENDS TRADING", layout="wide")

# ==========================================
# ==========================================
# 2. BASE DE DONNÉES ET CRÉATION DES TABLES (AVANT LA CONNEXION !)
# ==========================================
import psycopg2
import os
import streamlit as st

def get_connection():
    """Connexion PostgreSQL via Supabase Session Pooler."""
    return psycopg2.connect(
        st.secrets["supabase"]["db_url"],
        sslmode="require"
    )

# Connexion globale
conn = get_connection()
cursor = conn.cursor()

# --- Injection / Mise à jour de l'utilisateur administrateur (sécurisé via secrets) ---
with conn.cursor() as cur:
    # Vérifier si l'utilisateur ADG existe déjà
    cur.execute("SELECT COUNT(*) FROM utilisateurs WHERE username = 'ADG'")
    count = cur.fetchone()[0]

    # Récupérer le mot de passe depuis les secrets
    admin_password = st.secrets.get("admin", {}).get("password")
    if not admin_password:
        # Génération aléatoire si le secret n'est pas défini
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        admin_password = ''.join(secrets.choice(alphabet) for _ in range(12))
        print("=" * 60)
        print("🔐 ATTENTION : Le secret 'admin.password' n'est pas défini.")
        print("   Un mot de passe aléatoire a été généré automatiquement.")
        print(f"   Identifiant : ADG")
        print(f"   Mot de passe : {admin_password}")
        print("   Conservez ce mot de passe, ou définissez le secret pour le fixer.")
        print("=" * 60)

    password_hash = hashlib.sha256(admin_password.encode()).hexdigest()

    if count == 0:
        # Création du compte
        cur.execute("""
            INSERT INTO utilisateurs (username, password_hash, role, label)
            VALUES (%s, %s, %s, %s)
        """, ("ADG", password_hash, "Admin", "Administrateur"))
    else:
        # Mise à jour du mot de passe et des droits (si besoin)
        cur.execute("""
            UPDATE utilisateurs
            SET password_hash = %s, role = 'Admin', label = 'Administrateur'
            WHERE username = 'ADG'
        """, (password_hash,))
    conn.commit()

def log_action(action):
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO logs (date, action, utilisateur) VALUES (%s, %s, %s)",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), action, st.session_state.username)
            )
            conn.commit()
    except Exception as e:
        logging.error(f"Erreur log_action: {e}")

# ==========================================
# 3. SYSTÈME DE CONNEXION (SÉCURITÉ)
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.role = None
    st.session_state.username = None
    st.session_state.dernier_achat_traite = None

def authentifier():
    if not st.session_state.logged_in:

        # --- Styles globaux de la page de connexion ---
        st.markdown(
            """
            <style>
                #MainMenu, header, footer {visibility: hidden;}

                .stApp {
                    background: radial-gradient(circle at 20% 20%, #1a2332 0%, #0b0f19 55%, #060810 100%);
                }

                .block-container {
                    padding-top: 3rem;
                }

                .login-card {
                    background: linear-gradient(180deg, rgba(30,41,59,0.85), rgba(15,23,42,0.95));
                    border: 1px solid rgba(148, 163, 184, 0.15);
                    border-radius: 20px;
                    padding: 40px 40px 32px 40px;
                    box-shadow: 0 25px 60px rgba(0,0,0,0.45), inset 0 1px 0 rgba(255,255,255,0.04);
                    backdrop-filter: blur(6px);
                }

                .login-eyebrow {
                    text-align: center;
                    font-size: 11px;
                    font-weight: 700;
                    letter-spacing: 2.5px;
                    text-transform: uppercase;
                    color: #64748b;
                    margin-bottom: 6px;
                }

                .login-title {
                    text-align: center;
                    font-size: 26px;
                    font-weight: 800;
                    color: #f8fafc;
                    margin-bottom: 4px;
                    letter-spacing: -0.5px;
                }

                .login-subtitle {
                    text-align: center;
                    font-size: 13px;
                    color: #94a3b8;
                    margin-bottom: 28px;
                }

                div[data-testid="stForm"] {
                    border: none;
                    padding: 0;
                    background: transparent;
                }

                .stTextInput label {
                    font-size: 12px !important;
                    font-weight: 600 !important;
                    color: #cbd5e1 !important;
                    letter-spacing: 0.3px;
                }

                .stTextInput input {
                    border-radius: 10px !important;
                    border: 1px solid #334155 !important;
                    background-color: #1e293b !important;
                    color: #f1f5f9 !important;
                    padding: 10px 14px !important;
                }

                .stTextInput input:focus {
                    border-color: #6366f1 !important;
                    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15) !important;
                }

                div[data-testid="stFormSubmitButton"] button {
                    background: linear-gradient(135deg, #4f46e5, #4338ca) !important;
                    color: white !important;
                    border: none !important;
                    border-radius: 10px !important;
                    padding: 11px 0 !important;
                    font-weight: 700 !important;
                    letter-spacing: 0.3px;
                    margin-top: 8px;
                    box-shadow: 0 8px 20px rgba(79, 70, 229, 0.35);
                    transition: all 0.15s ease;
                }

                div[data-testid="stFormSubmitButton"] button:hover {
                    box-shadow: 0 10px 26px rgba(79, 70, 229, 0.5);
                    transform: translateY(-1px);
                }

                .login-footer {
                    text-align: center;
                    margin-top: 22px;
                    font-size: 11px;
                    color: #475569;
                    letter-spacing: 0.3px;
                }
            </style>
            """,
            unsafe_allow_html=True
        )

        # On utilise des colonnes pour centrer le formulaire
        col1, col2, col3 = st.columns([1, 1.5, 1])

        with col2:
            st.write("")
            st.write("")

            st.markdown('<div class="login-card">', unsafe_allow_html=True)

            # Logo s'il existe
            if os.path.exists("Logo-FCC.png"):
                col_logo1, col_logo2, col_logo3 = st.columns([1, 1, 1])
                with col_logo2:
                    st.image("Logo-FCC.png", use_container_width=True)
                st.write("")

            st.markdown('<div class="login-eyebrow">Accès sécurisé</div>', unsafe_allow_html=True)
            st.markdown('<div class="login-title">Espace ERP</div>', unsafe_allow_html=True)
            st.markdown('<div class="login-subtitle">Connectez-vous pour accéder à votre plateforme de gestion</div>', unsafe_allow_html=True)

            with st.form("login_form"):
                user = st.text_input("IDENTIFIANT", placeholder="Entrez votre identifiant")
                pwd = st.text_input("MOT DE PASSE", type="password", placeholder="••••••••")
                submit = st.form_submit_button("Se connecter →", use_container_width=True)

                if submit:
                    pwd_hash = hashlib.sha256(pwd.encode()).hexdigest()
                    cursor.execute("""
                        SELECT role, label, permissions, username FROM utilisateurs 
                        WHERE username = %s AND password_hash = %s
                    """, (user.strip(), pwd_hash))
                    record = cursor.fetchone()

                    if record:
                        st.session_state.logged_in = True
                        st.session_state.role = record[0]
                        st.session_state.username = record[1]
                        st.session_state.permissions_raw = record[2]
                        st.session_state.username_id = record[3]
                        st.rerun()
                    else:
                        st.error("❌ Identifiants incorrects.")

            st.markdown('</div>', unsafe_allow_html=True)  # fin .login-card

            st.markdown(
                '<div class="login-footer">🔒 Connexion chiffrée · Toute activité est journalisée</div>',
                unsafe_allow_html=True
            )

        st.stop()

authentifier()
# ==========================================
# 4. FONCTIONS UTILITAIRES ET PDF
# ==========================================
import hashlib
import secrets
import qrcode
from io import BytesIO
from PIL import Image
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

def calculer_hash_pdf(pdf_bytes: bytes) -> str:
    """Calcule l'empreinte SHA-256 d'un PDF."""
    return hashlib.sha256(pdf_bytes).hexdigest()

def generer_code_verification() -> str:
    """Génère un code court unique et lisible pour vérification manuelle."""
    return secrets.token_hex(4).upper()  # ex: 'A1B2C3D4'

def generer_qr_code(donnees: str, taille: int = 200) -> Image.Image:
    """Génère une image QR code (PIL Image) à partir d'une chaîne de caractères."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(donnees)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    return img.resize((taille, taille))

def apposer_qr_sur_pdf(pdf_bytes: bytes, code_verification: str, reference: str) -> bytes:
    """
    Ajoute un QR code + texte de vérification en bas à droite de la DERNIÈRE page du PDF.
    Le QR encode le code de vérification.
    """
    # Contenu encodé dans le QR
    contenu_qr = f"REF:{reference}|CODE:{code_verification}"
    qr_img = generer_qr_code(contenu_qr, taille=120)  # taille réduite pour ne pas prendre trop de place

    qr_buffer = BytesIO()
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)

    # Création d'un calque (overlay) avec reportlab
    overlay_buffer = BytesIO()
    c = canvas.Canvas(overlay_buffer, pagesize=A4)

    # Position : bas à droite de la page (coordonnées en points, 1 point = 1/72 inch)
    # A4 fait 595 x 842 points. On place le QR à x=450, y=80 (80 points depuis le bas)
    x_qr = 470
    y_qr = 115          # ← plus haut
    largeur_qr = 70     # ← un peu plus petit
    c.drawImage(ImageReader(qr_img), x_qr, y_qr, width=largeur_qr, height=largeur_qr)

    # Texte sous le QR code (pour référence)
    c.setFont("Helvetica", 6)
    c.drawString(x_qr - 5, y_qr - 10, f"Réf: {reference}")
    c.drawString(x_qr - 5, y_qr - 20, f"Code: {code_verification}")
    c.drawString(x_qr - 5, y_qr - 30, "Vérifiable dans l'ERP")

    c.save()
    overlay_buffer.seek(0)

    # Fusion overlay + PDF original (dernière page uniquement)
    pdf_original = PdfReader(BytesIO(pdf_bytes))
    pdf_overlay = PdfReader(overlay_buffer)
    writer = PdfWriter()

    nb_pages = len(pdf_original.pages)
    for i, page in enumerate(pdf_original.pages):
        if i == nb_pages - 1:  # dernière page uniquement
            page.merge_page(pdf_overlay.pages[0])
        writer.add_page(page)

    resultat = BytesIO()
    writer.write(resultat)
    return resultat.getvalue()
def convertir_df_csv(df):
    return df.to_csv(index=False).encode("utf-8")

def afficher_pdf(pdf_bytes):
    """Génère une iframe HTML pour afficher un PDF en mémoire (Bytes)."""
    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="500" type="application/pdf"></iframe>'
    st.markdown(pdf_display, unsafe_allow_html=True)
    
def convertir_df_excel(df):
    """Convertit un DataFrame en bytes Excel (nécessite openpyxl)."""
    from io import BytesIO
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Donnees')
    return output.getvalue()

def _clean_text(text):
    """Nettoie et sécurise les chaînes pour éviter les crashs d'encodage FPDF standard."""
    if not isinstance(text, str):
        return str(text)
    text = text.replace("•", "-")
    text = text.replace("\u2019", "'").replace("\u2018", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return text

def telecharger_pdf_puis_supprimer(fichier_ou_bytes, label, nom_fichier_export="Document.pdf"):
    """
    Gère le téléchargement d'un PDF, qu'il soit sur le disque (chemin) ou déjà en mémoire (bytes).
    """
    try:
        # CAS 1 : Le document est déjà en mémoire (Bytes)
        if isinstance(fichier_ou_bytes, bytes):
            st.download_button(
                label=label,
                data=fichier_ou_bytes,
                file_name=nom_fichier_export, 
                mime="application/pdf"
            )
            
        # CAS 2 : Le document est un fichier sur le disque dur (Texte/Chemin)
        else:
            with open(fichier_ou_bytes, "rb") as f:
                data = f.read()
                
            st.download_button(
                label=label,
                data=data,
                file_name=nom_fichier_export, 
                mime="application/pdf"
            )
            os.remove(fichier_ou_bytes) # On supprime le fichier temporaire
            
    except Exception as e:
        st.error(f"Erreur de traitement du fichier PDF : {e}")
def _set_font_safely(pdf, style="", size=10):
    font_path = "DejaVuSans.ttf"
    if os.path.exists(font_path):
        try:
            pdf.add_font("DejaVu", "", font_path)
        except Exception:
            pass
    try:
        pdf.set_font("DejaVu", style, size)
    except Exception:
        pdf.set_font("Arial", style, size)


class ContratPDF(FPDF):
    def footer(self):
        # 2. PIED DE PAGE
        self.set_y(-35)
        footer_path = "Footer-FCC.png"
        if os.path.exists(footer_path):
            try:
                self.image(footer_path, x=10, y=self.get_y(), w=165)
            except Exception as e:
                print(f"Erreur footer Contrat : {e}")
        else:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, "[Image de pied de page manquante : Footer-FCC.png]", align="C")


class BonPaiementPDF(FPDF):
    def footer(self):
        # 2. PIED DE PAGE
        self.set_y(-40)
        footer_path = "Footer-FCC.png"
        if os.path.exists(footer_path):
            try:
                self.image(footer_path, x=10, y=self.get_y(), w=165)
            except Exception as e:
                print(f"Erreur footer BonPaiement : {e}")
        else:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(150, 150, 150)
            self.cell(0, 10, "[Image de pied de page manquante : Footer-FCC.png]", align="C")

class CommercialInvoicePDF(FPDF):
    def footer(self):
        self.set_y(-35)
        try:
            self.image("Footer-FCC.png", x=10, y=self.get_y(), w=190)
        except:
            self.set_font("Arial", "I", 8)
            self.set_text_color(148, 163, 184)
            self.cell(0, 10, "FRIENDS CAMEROON COMMODITIES - Tous droits réservés / All rights reserved", align="C")


# --- 2. FONCTION DE GÉNÉRATION DU PDF ---
def generer_pdf_international(
    id_doc,
    date_str,
    client,
    qte,
    pu,
    total,
    devise="XAF",
    cachet_blob=None,
    incoterm="FOB",
    port_depart="Port de Kribi, Cameroun",
    port_arrivee="",
    condition_paiement="",
    banque_nom="",
    banque_swift="",
    banque_iban="",
    banque_numero_compte="",
    pays_origine="Cameroun",
    numero_lot="",
    poids_brut=None,
    poids_net=None,
    nb_colis="",
    conditionnement="Sacs de jute 60kg",
    poids_sac_kg=0.5,
    hs_code="1801.00",
    numero_commande="",
):
    """
    Génère une Commercial Invoice sur UNE page, conforme aux standards
    douaniers export (mentions HS Code, pays d'origine, poids, colisage)
    exigés par la plupart des administrations douanières et banques
    (crédit documentaire / lettre de crédit).

    Corrections apportées vs version initiale :
    - Tient sur 1 page (marges et interlignes resserrés, zone signature
      remontée juste après le tableau bancaire au lieu d'être poussée
      en bas de page).
    - Ajout des mentions export obligatoires/standards : Country of
      Origin, HS Code, poids brut/net, nombre et type de colis,
      référence commande client.
    - Le bloc TOTAL DUE est aligné avec le tableau des marchandises
      (même grille de colonnes) au lieu d'être positionné en absolu.
    - Prix unitaire affiché avec la devise (ex: "2,500.00 XAF / kg")
      plutôt qu'un nombre nu, ambigu en audit.
    - Gestion propre du cas où `total()` en toutes lettres échoue
      (fallback silencieux, sans dépendance obligatoire).
    - Le cachet est positionné de façon relative (pdf.get_y()) et non
      en coordonnées absolues, ce qui évite tout chevauchement si le
      contenu au-dessus varie en hauteur.
    """
    #--- Calculs automatiques si certaines valeurs sont manquantes ---
    if poids_net is None:
        poids_net = qte
    if poids_brut is None:
        # Si on a le nombre de colis, on ajoute le poids des sacs
        if nb_colis is not None and nb_colis > 0:
            poids_brut = poids_net + (nb_colis * poids_sac_kg)
        else:
            poids_brut = poids_net   # fallback
    if nb_colis is None:
        # Estimation à partir du conditionnement standard (60 kg/sac)
        if conditionnement and "60kg" in conditionnement:
            nb_colis = int(poids_net / 60) if poids_net > 0 else 0
        else:
            nb_colis = 0
            
    pdf = CommercialInvoicePDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)

    #    # ------------------------------------------------------------------
    # BLOC 1 — EN-TÊTE (LOGO & TITRE)
    # ------------------------------------------------------------------
    try:
        pdf.image("Logo-FCC.png", x=10, y=10, w=36)
    except Exception:
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(30, 41, 59)
        pdf.set_xy(10, 12)
        pdf.cell(60, 8, "FRIENDS CAMEROON COMMODITIES", ln=0)

    pdf.set_xy(110, 12)
    pdf.set_font("Arial", "B", 20)
    pdf.set_text_color(15, 23, 42)
    pdf.cell(90, 8, "COMMERCIAL INVOICE", ln=1, align="R")

    pdf.set_xy(110, 21)
    pdf.set_font("Arial", "B", 9)
    pdf.set_text_color(100, 116, 139)
    pdf.cell(90, 5, f"INVOICE NO. : INV-{id_doc:04d}", ln=1, align="R")
    pdf.set_x(110)
    pdf.cell(90, 5, f"DATE : {date_str}", ln=1, align="R")
    if numero_commande:
        pdf.set_x(110)
        pdf.cell(90, 5, f"P.O./ORDER REF : {numero_commande}", ln=1, align="R")

    pdf.set_y(38)
    pdf.set_draw_color(226, 232, 240)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # ------------------------------------------------------------------
    # BLOC 2 — ADRESSES (ÉMETTEUR & CLIENT) – bilingue
    # ------------------------------------------------------------------
    y_infos = pdf.get_y()

    pdf.set_xy(10, y_infos)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(90, 4.5, "ÉMETTEUR / EXPORTER", ln=1)
    pdf.set_x(10)
    pdf.set_font("Arial", "B", 10.5)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(90, 5, "FRIENDS CAMEROON COMMODITIES", ln=1)
    pdf.set_x(10)
    pdf.set_font("Arial", "", 8.5)
    pdf.cell(90, 4.2, "Douala, Région du Littoral, Cameroun", ln=1)
    pdf.set_x(10)
    pdf.cell(90, 4.2, "Email : infos@friendscameroon.cm", ln=1)
    pdf.set_x(10)
    pdf.cell(90, 4.2, f"Country of Origin / Pays d'origine : {pays_origine}", ln=1)

    pdf.set_xy(110, y_infos)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(148, 163, 184)
    pdf.cell(90, 4.5, "FACTURÉ À / BILLED TO", ln=1)

    nom_c = client.get("nom", "Client Inconnu")
    pdf.set_x(110)
    pdf.set_font("Arial", "B", 10.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(90, 5, nom_c)

    pdf.set_font("Arial", "", 8.5)
    if client.get("email"):
        pdf.set_x(110)
        pdf.cell(90, 4.2, f"Email : {client['email']}", ln=1)
    if client.get("pays"):
        pdf.set_x(110)
        pdf.cell(90, 4.2, f"Destination / Pays : {client['pays']}", ln=1)
    if client.get("nui"):
        pdf.set_x(110)
        pdf.cell(90, 4.2, f"Tax ID / VAT (NUI) : {client['nui']}", ln=1)

    pdf.ln(6)

    # ------------------------------------------------------------------
    # BLOC 3 — DÉTAILS D'EXPORTATION (2 rangées) – bilingue
    # ------------------------------------------------------------------
    y_box = pdf.get_y()
    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(226, 232, 240)
    pdf.rect(10, y_box, 190, 24, "DF")

    # Ligne 1 : Incoterm, ports, devise, HS Code
    pdf.set_xy(10, y_box + 2)
    pdf.set_font("Arial", "B", 7.3)
    pdf.set_text_color(100, 116, 139)
    for label, w in [("Incoterm", 38), ("Port of Loading / Embarquement", 48),
                     ("Port of Discharge / Déchargement", 48), ("Devise / Currency", 28), ("HS Code", 28)]:
        pdf.cell(w, 4.5, label, align="C")
    pdf.ln(4.5)

    pdf.set_x(10)
    pdf.set_font("Arial", "B", 8.5)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(38, 5.5, incoterm, align="C")
    pdf.cell(48, 5.5, port_depart, align="C")
    pdf.cell(48, 5.5, port_arrivee if port_arrivee else "TBD", align="C")
    pdf.cell(28, 5.5, devise, align="C")
    pdf.cell(28, 5.5, hs_code, align="C")
    pdf.ln(7)

    # Ligne 2 : Poids, emballage, colis
    pdf.set_x(10)
    pdf.set_font("Arial", "B", 7.3)
    pdf.set_text_color(100, 116, 139)
    for label, w in [("Gross Weight / Poids Brut", 38), ("Net Weight / Poids Net", 48),
                     ("Packaging / Emballage", 48), ("No. of Packages / Nb Colis", 28), ("", 28)]:
        pdf.cell(w, 4.5, label, align="C")
    pdf.ln(4.5)

    pdf.set_x(10)
    pdf.set_font("Arial", "B", 8.5)
    pdf.set_text_color(30, 41, 59)
    poids_brut_txt = f"{poids_brut:,.2f} kg" if poids_brut else f"{qte:,.2f} kg"
    poids_net_txt = f"{poids_net:,.2f} kg" if poids_net else f"{qte:,.2f} kg"
    pdf.cell(38, 5.5, poids_brut_txt, align="C")
    pdf.cell(48, 5.5, poids_net_txt, align="C")
    pdf.cell(48, 5.5, conditionnement, align="C")
    pdf.cell(28, 5.5, str(nb_colis) if nb_colis and nb_colis > 0 else "-", align="C")
    pdf.cell(28, 5.5, "", align="C")
    pdf.ln(9)

    # ------------------------------------------------------------------
    # BLOC 4 — TABLEAU DES MARCHANDISES
    # ------------------------------------------------------------------
    pdf.set_font("Arial", "B", 9.5)
    pdf.set_fill_color(15, 23, 42)
    pdf.set_text_color(255, 255, 255)
    pdf.set_draw_color(15, 23, 42)

    col_desc, col_qty, col_pu, col_total = 70, 30, 45, 45

    pdf.cell(col_desc, 9, " Description of Goods", border=1, fill=True)
    pdf.cell(col_qty, 9, "Qty (kg)", border=1, align="C", fill=True)
    pdf.cell(col_pu, 9, f"Unit Price ({devise})", border=1, align="C", fill=True)
    pdf.cell(col_total, 9, f"Total ({devise})", border=1, align="C", fill=True)
    pdf.ln()

    pdf.set_font("Arial", "", 9.5)
    pdf.set_text_color(30, 41, 59)

    desc_marchandise = " Cacao (Fèves / Cocoa Beans)"
    if numero_lot:
        desc_marchandise += f"\n Lot n° {numero_lot}"

    y_row = pdf.get_y()
    pdf.multi_cell(col_desc, 11 if numero_lot else 11, desc_marchandise, border="LR")
    y_after_desc = pdf.get_y()
    row_h = y_after_desc - y_row

    pdf.set_xy(10 + col_desc, y_row)
    pdf.cell(col_qty, row_h, f"{qte:,.2f}", border="LR", align="C")
    pdf.cell(col_pu, row_h, f"{pu:,.2f}", border="LR", align="C")
    pdf.cell(col_total, row_h, f"{total:,.2f}", border="LR", align="R")
    pdf.set_y(y_after_desc)

    pdf.cell(col_desc + col_qty + col_pu + col_total, 0, "", border="T", ln=1)

    # ------------------------------------------------------------------
    # BLOC 5 — TOTAL (aligné sur la grille du tableau ci-dessus)
    # ------------------------------------------------------------------
    pdf.ln(4)
    pdf.set_x(10 + col_desc + col_qty)
    pdf.set_font("Arial", "B", 11)
    pdf.set_fill_color(241, 245, 249)
    pdf.set_draw_color(203, 213, 225)
    pdf.cell(col_pu, 9, "TOTAL DUE", border=1, fill=True, align="C")
    pdf.cell(col_total, 9, f"{total:,.2f} {devise}", border=1, align="R", fill=True)
    pdf.ln(11)

    pdf.set_x(10)
    pdf.set_font("Arial", "B", 8.5)
    pdf.cell(0, 4.5, "Arrêtée à la somme de / Amount in words :", ln=1)
    pdf.set_x(10)
    pdf.set_font("Arial", "I", 9.5)

    try:
        from num2words import num2words
        nom_devise = "Francs CFA" if devise == "XAF" else devise
        montant_lettres = f"{num2words(int(total), lang='fr').capitalize()} {nom_devise}."
    except Exception:
        montant_lettres = "_" * 90

    pdf.multi_cell(190, 5, montant_lettres)
    pdf.ln(4)

    # ------------------------------------------------------------------
    # BLOC 6 — CONDITIONS & COORDONNÉES BANCAIRES
    # ------------------------------------------------------------------
    pdf.set_x(10)
    pdf.set_font("Arial", "B", 9)
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(203, 213, 225)
    pdf.cell(190, 6.5, " Conditions de Paiement & Coordonnées Bancaires", border="LTR", fill=True, ln=1)

    pdf.set_font("Arial", "", 8.5)
    pdf.set_x(10)
    pdf.cell(190, 5.2, f"  Termes de paiement : {condition_paiement}", border="LR", ln=1)
    pdf.set_x(10)
    pdf.cell(190, 5.2, f"  Banque / Bank : {banque_nom}", border="LR", ln=1)
    pdf.set_x(10)
    pdf.cell(190, 5.2, f"  Numéro de compte / Account Number : {banque_numero_compte}", border="LR", ln=1)
    pdf.set_x(10)
    pdf.cell(190, 5.2, f"  Code SWIFT / BIC : {banque_swift}   |   IBAN : {banque_iban}", border="LR", ln=1)
    pdf.set_x(10)
    pdf.cell(190, 5.2, "  Nom du compte / Account Name : FRIENDS CAMEROON COMMODITIES", border="LBR", ln=1)

    pdf.ln(6)

    # ------------------------------------------------------------------
    # BLOC 7 — MENTION LÉGALE + SIGNATURE (compact, reste sur la page 1)
    # ------------------------------------------------------------------
    pdf.set_x(10)
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(100, 116, 139)
    pdf.multi_cell(
        190, 3.8,
        "Nous certifions que les informations contenues dans cette facture sont exactes et "
        "que les marchandises décrites ci-dessus sont d'origine Cameroun, sauf indication contraire.\n"
        "We certify that the information on this invoice is true and correct and that the goods "
        "described above originate from Cameroon unless otherwise stated.",
    )
    pdf.ln(4)

    y_signatures = pdf.get_y()
    pdf.set_x(110)
    pdf.set_font("Arial", "B", 9.5)
    pdf.set_text_color(30, 41, 59)
    pdf.multi_cell(
        90, 4.6,
        "Pour la Direction,\nFRIENDS CAMEROON COMMODITIES\n\n\n\n___________________________\nVisa & Cachet de la Direction",
        align="C",
    )

    if cachet_blob:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                tmp_file.write(cachet_blob)
                tmp_path = tmp_file.name
            pdf.image(tmp_path, x=122.5, y=y_signatures + 10, w=60)
            os.remove(tmp_path)
        except Exception as e:
            print(f"Erreur lors de l'insertion du cachet : {e}")

    filename = f"Commercial_Invoice_{id_doc}.pdf"
    pdf.output(filename)

    return filename

def calculer_refractions_avec_coeff(
    poids_net,
    humidite,
    taux_debris,
    taux_etrangers,
    taux_plates,
    taux_mdc,
    seuils=None,
    refaction_humidite_pct=0.72   # valeur fixe en % du poids net, si excédent
):
    """
    Calcule les réfactions :
      - Humidité : si excédent > 0, on déduit un pourcentage fixe (par défaut 0.72%)
      - Autres : on déduit proportionnellement à l'excédent (en %)
    """
    if seuils is None:
        seuils = {
            'humidite': 8.0,
            'debris': 1.5,
            'etrangers': 0.75,
            'plates': 1.5,
            'mdc': 3.0
        }

    # 1. Calcul des excédents (en points de pourcentage)
    exces = {
        'humidite': max(0, humidite - seuils['humidite']),
        'debris': max(0, taux_debris - seuils['debris']),
        'etrangers': max(0, taux_etrangers - seuils['etrangers']),
        'plates': max(0, taux_plates - seuils['plates']),
        'mdc': max(0, taux_mdc - seuils['mdc'])
    }

    # 2. Réfaction en poids pour chaque catégorie
    ref_par_cat = {}
    total_ref = 0.0

    for cat, ex in exces.items():
        if ex > 0:
            if cat == 'humidite':
                # Réfaction fixe : poids_net * 0.72 / 100
                ref = poids_net * refaction_humidite_pct / 100.0
            else:
                # Réfaction proportionnelle à l'excédent
                ref = poids_net * ex / 100.0
            ref_par_cat[cat] = ref
            total_ref += ref

    poids_net_paye = max(0.0, poids_net - total_ref)

    return {
        'excès': exces,
        'réfactions_détaillées': ref_par_cat,
        'total_réfaction': total_ref,
        'poids_net_payable': poids_net_paye,
        'taux_réfaction_pct': (total_ref / poids_net * 100) if poids_net > 0 else 0,
    }
    
def enregistrer_analyse_et_sync_achat(conn, id_achat, humidite, moisies, ardoises,
                                      mitees, germees, violettes, white_spots, 
                                      poids_net, taux_debris, taux_etrangers,
                                      taux_plates, taux_mdc):
    """
    Insère les résultats d’analyse et met à jour la table achats
    avec le poids net payable calculé à partir des réfactions.
    """
    cursor = conn.cursor()

    # 1. Insertion / mise à jour complète dans analyses_qualite
    sql_analyse = """
    INSERT INTO analyses_qualite (
        id_achat, humidite, feves_moisies, feves_ardoisees,
        feves_mitees, feves_germees, feves_violettes_c1,
        white_spots_c1, autres_defauts
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id_achat) DO UPDATE SET
        humidite = EXCLUDED.humidite,
        feves_moisies = EXCLUDED.feves_moisies,
        feves_ardoisees = EXCLUDED.feves_ardoisees,
        feves_mitees = EXCLUDED.feves_mitees,
        feves_germees = EXCLUDED.feves_germees,
        feves_violettes_c1 = EXCLUDED.feves_violettes_c1,
        white_spots_c1 = EXCLUDED.white_spots_c1
    """
    cursor.execute(sql_analyse, (
        id_achat, humidite, moisies, ardoises,
        mitees, germees, violettes, white_spots
    ))

    # 2. Calcul des réfactions (uniquement sur les critères retenus)
    #    On suppose que taux_debris, taux_etrangers, taux_plates, taux_mdc sont disponibles
    ref_result = calculer_refractions_avec_coeff(
        poids_net=poids_net,
        humidite=humidite,
        taux_debris=taux_debris,
        taux_etrangers=taux_etrangers,
        taux_plates=taux_plates,
        taux_mdc=taux_mdc)
    poids_net_paye = ref_result['poids_net_payable']
    total_ref = ref_result['total_réfaction']

    # 3. Mise à jour de la table achats
    sql_achat = """
        UPDATE achats 
        SET poids_net = %s, deductions = %s 
        WHERE id = %s
    """
    cursor.execute(sql_achat, (poids_net_paye, total_ref, id_achat))

    conn.commit()
    return ref_result  # optionnel : pour réutilisation

def generer_bon_paiement_pdf(
    data_paiement, type_document=None, signataire=("DG", "DGD"), cachet_blob=None
):
    """Génère un PDF professionnel et personnalisé selon le contexte.

    type_document peut valoir :
    - 'bon_paiement'       : Se concentre uniquement sur l'acompte décaissé ce
    jour.
    - 'engagement_dette'   : Met en évidence le Net, les déductions et le RESTE
    À PAYER.
    - 'reglement_dette'    : Utilisé pour le remboursement ultérieur d'une
    dette.
    """
    pdf = BonPaiementPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=30)
    # 1. LOGO DE L'ENTREPRISE
    try:
        pdf.image("Logo-FCC.png", x=10, y=5, w=60)
    except FileNotFoundError:
        pass

    pdf.set_y(35)
    
    # 2. QR CODE D'AUTHENTICITÉ (Haut Droite - Si disponible)
    code_verif = data_paiement.get("code_verification") or data_paiement.get("code_verif")
    if code_verif:
            try:
                # Génération du QR code en image temporaire
                qr_data = f"Ref: {data_paiement.get('num', '')} | Code: {code_verif}"
                qr = qrcode.QRCode(box_size=4, border=1)
                qr.add_data(qr_data)
                qr.make(fit=True)
                qr_img = qr.make_image(fill_color="black", back_color="white")
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_qr:
                    qr_img.save(tmp_qr.name)
                    tmp_qr_path = tmp_qr.name
                # Affichage du QR code (Coin supérieur droit : x=165, y=8, largeur=28mm)
                pdf.image(tmp_qr_path, x=165, y=8, w=28)
                # Mention du code sous le QR Code
                pdf.set_xy(155, 37)
                pdf.set_font("Times", "B", 8)
                pdf.cell(48, 4, _clean_text(f"Code : {code_verif}"), align="C")
                os.remove(tmp_qr_path)
            except Exception as e:
                print(f"Erreur d'insertion du QR Code : {e}")

    # --- DÉTERMINATION DU TYPE DE DOCUMENT ---
    # Rétrocompatibilité avec l'ancien système de flags
    if type_document == "bon_caisse":
        type_document = "bon_paiement"
    if not type_document:
        is_reliquat = data_paiement.get(
            "type_bon"
        ) == "reliquat" or data_paiement.get("is_reliquat", False)
        type_document = "reglement_dette" if is_reliquat else "bon_paiement"

    # --- ENRICHISSEMENT AUTOMATIQUE DES DONNÉES DEPUIS LA BD ---
    fournisseur_nom = data_paiement.get("fournisseur", "")
    num_lot = data_paiement.get("num_lot", "______")
    num_contrat = data_paiement.get("num_contrat", "")
    num_bon = data_paiement.get("num_paiement", "______")

    # Gestion sécurisée de la date
    if "date" in data_paiement and data_paiement["date"]:
        date_bon = data_paiement["date"]
    else:
        date_bon = datetime.now().strftime("%d/%m/%Y")

    fournisseur_info = {
        "nom": fournisseur_nom,
        "telephone": "N/A",
        "ville": "N/A",
        "rccm": "N/A",
        "adresse": "N/A",
        "nui": "N/A",
        "compte": data_paiement.get("num_compte", "N/A"),
    }

    # Récupération automatique du fournisseur en base (CORRIGÉ AVEC fetch_one)
    if fournisseur_nom:
        try:
            res = fetch_one(
                """
                SELECT nom, telephone, ville, Rccm, adresse, numero_de_compte, nui 
                FROM fournisseurs 
                WHERE nom = %s
            """,
                (fournisseur_nom,),
            )
            if res:
                fournisseur_info["nom"] = res[0] or fournisseur_nom
                fournisseur_info["telephone"] = res[1] or "N/A"
                fournisseur_info["ville"] = res[2] or "N/A"
                fournisseur_info["rccm"] = res[3] or "N/A"
                fournisseur_info["adresse"] = res[4] or "N/A"
                fournisseur_info["compte"] = (
                    data_paiement.get("num_compte") or res[5] or "N/A"
                )
                fournisseur_info["nui"] = res[6] or "N/A"
        except Exception as e:
            logging.error(f"Erreur recup fournisseur PDF: {e}")

    # Récupération de l'achat (CORRIGÉ AVEC fetch_one)
    if num_lot and num_lot != "______":
        try:
            row = fetch_one(
                """
                SELECT quantite_kg, prix_unitaire, total, montant_avance, poids_net, numero_contrat, deductions, libelle_deductions
                FROM achats 
                WHERE numero_de_lot = %s
            """,
                (num_lot,),
            )
            if row:
                if "quantite_kg" not in data_paiement or not data_paiement.get("quantite_kg"):
                    data_paiement["quantite_kg"] = row[0]
                if "prix_unitaire" not in data_paiement or not data_paiement.get("prix_unitaire"):
                    data_paiement["prix_unitaire"] = row[1]
                if "total" not in data_paiement or not data_paiement.get("total"):
                    data_paiement["total"] = row[2]

                # CORRECTION : On récupère l'avance peu importe le type de document si non spécifié
                if not any(data_paiement.get(k) for k in ["versement", "montant", "montant_paye", "montant_verse"]):
                    data_paiement["versement"] = row[3] if row[3] is not None else 0.0

                if "poids_net" not in data_paiement or not data_paiement.get("poids_net"):
                    data_paiement["poids_net"] = row[4]
                if not num_contrat or num_contrat in ["______", "N/A", ""]:
                    num_contrat = row[5] or "______"
                if "deductions" not in data_paiement:
                    data_paiement["deductions"] = row[6] if row[6] else 0.0
                if "libelle_deductions" not in data_paiement:
                    data_paiement["libelle_deductions"] = row[7] if row[7] else ""
        except Exception as e:
            logging.error(f"Erreur recup achat PDF: {e}")


    # Variables financières robustes (gestion de plusieurs clés possibles)
    pu = float(data_paiement.get("prix_unitaire", data_paiement.get("pu", 0)))
    qte = float(data_paiement.get("quantite_kg", data_paiement.get("qte", 0)))
    valeur_brute = pu * qte
    
    # Recherche élargie du versement
    versement = float(
        data_paiement.get("versement") or 
        data_paiement.get("montant") or 
        data_paiement.get("montant_paye") or 
        data_paiement.get("montant_verse") or 
        0.0
    )
    if versement == 0.0 and 'valeurbrute' in locals() and valeur_brute > 0:
        versement = valeur_brute
    
    poids_net = data_paiement.get("poids_net", f"{qte:,.2f}")

    deductions = float(data_paiement.get("deductions", 0.0))
    libelle_deductions = data_paiement.get(
        "libelle_deductions", "Déductions (Transport/Avances)"
    )
    if not libelle_deductions:
        libelle_deductions = "Déductions (Transport/Avances)"

    # --- DÉFINITIONS DU TITRE SELON LE MODE ---
    titres = {
        "bon_paiement": "BON DE PAIEMENT (ACOMPTE)",
        "bon_caisse": "BON DE PAIEMENT (ACOMPTE)",
        "engagement_dette": "ENGAGEMENT DE REGLEMENT (RESTE A PAYER)",
        "reglement_dette": "REÇU DE REGLEMENT DE DETTE",
    }
    titre_document = titres.get(type_document, "BON DE PAIEMENT")

    # 2. EN-TÊTE : DEUX COLONNES CÔTE À CÔTE
    y_top_header = pdf.get_y()

    # --- À GAUCHE : RÉFÉRENCES ---
    pdf.set_xy(10, y_top_header)
    _set_font_safely(pdf, "B", 13)
    pdf.set_text_color(30, 41, 59)
    pdf.cell(90, 8, _clean_text(titre_document), ln=1)

    curr_y_gauche = y_top_header + 10
    references = [
        ("Numéro :", num_bon),
        ("Date :", date_bon),
        ("N° Contrat :", num_contrat),
        ("N° Lot :", num_lot),
    ]
    for label, val in references:
        pdf.set_xy(10, curr_y_gauche)
        _set_font_safely(pdf, "B", 9.5)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(25, 5.5, _clean_text(label))
        _set_font_safely(pdf, "", 9.5)
        pdf.set_text_color(30, 41, 59)
        pdf.cell(65, 5.5, _clean_text(f"{val}"), ln=1)
        curr_y_gauche += 5.5

    # --- À DROITE : INFOS DU FOURNISSEUR ---
    x_bloc = 120
    largeur_label, largeur_valeur = 22, 53
    largeur_totale = largeur_label + largeur_valeur

    pdf.set_xy(x_bloc, y_top_header)
    pdf.set_fill_color(245, 245, 245)
    pdf.set_draw_color(180, 180, 180)
    _set_font_safely(pdf, "B", 9)
    pdf.cell(
        largeur_totale,
        4,
        _clean_text(" INFORMATIONS DU FOURNISSEUR"),
        border=1,
        ln=1,
        fill=True,
    )

    infos_f = [
        ("Nom :", fournisseur_info["nom"]),
        ("Tél :", fournisseur_info["telephone"]),
        ("Ville :", fournisseur_info["ville"]),
        ("RCCM :", fournisseur_info["rccm"]),
        ("Adresse :", fournisseur_info["adresse"]),
        ("N° Compte :", fournisseur_info["compte"]),
        ("NUI :", fournisseur_info["nui"]),
    ]
    curr_y_droite = y_top_header + 4
    for label, val in infos_f:
        pdf.set_xy(x_bloc, curr_y_droite)
        _set_font_safely(pdf, "B", 8.5)
        pdf.cell(largeur_label, 4.5, _clean_text(f" {label}"), border="LTB")
        _set_font_safely(pdf, "", 8.5)
        pdf.cell(largeur_valeur, 4.5, _clean_text(f" {val}"), border="RTB", ln=1)
        curr_y_droite += 4.5

    pdf.set_y(max(curr_y_gauche, curr_y_droite) + 6)

    # 3. TABLEAU 1 : DÉTAILS DE LA MARCHANDISE
    _set_font_safely(pdf, "B", 10)
    pdf.set_fill_color(230, 245, 230)
    pdf.set_draw_color(120, 120, 120)

    pdf.cell(70, 8, " DESIGNATION", border=1, fill=True, align="L")
    pdf.cell(40, 8, "PRIX / KG", border=1, fill=True, align="C")
    pdf.cell(40, 8, "QUANTITE", border=1, fill=True, align="C")
    pdf.cell(40, 8, "MONTANT BRUT", border=1, fill=True, align="C")
    pdf.ln()

    _set_font_safely(pdf, "", 10)
    prefix_desig = (
        "Règlement Reliquat -"
        if type_document == "reglement_dette"
        else "Achat Cacao -"
    )
    designation_text = f" {prefix_desig} Lot N° {num_lot}"
    pdf.cell(70, 8, _clean_text(designation_text), border=1, align="L")
    pdf.cell(40, 8, f"{pu:,.0f} FCFA", border=1, align="C")
    pdf.cell(40, 8, f"{qte:,.2f} kg", border=1, align="C")
    pdf.cell(40, 8, f"{valeur_brute:,.0f} FCFA", border=1, ln=1, align="C")

    # SOUS-TOTAL
    pdf.set_fill_color(245, 245, 245)
    _set_font_safely(pdf, "B", 10)
    pdf.cell(150, 7, "POIDS NET : ", border=1, fill=True, align="R")
    pdf.cell(40, 7, f"{poids_net} kg ", border=1, ln=1, fill=True, align="R")
    pdf.cell(150, 7, "VALEUR DU LOT BRUT : ", border=1, fill=True, align="R")
    pdf.cell(
        40, 7, f"{valeur_brute:,.0f} FCFA ", border=1, ln=1, fill=True, align="R"
    )
    pdf.ln(5)

    # 4. TABLEAU 2 : SITUATION FINANCIÈRE PERSONNALISÉE
    _set_font_safely(pdf, "B", 11)
    pdf.cell(0, 6, _clean_text("SITUATION COMPTABLE ET RÈGLEMENT"), ln=1)
    pdf.ln(2)

    pdf.set_fill_color(230, 240, 250)
    _set_font_safely(pdf, "B", 10)
    pdf.cell(110, 8, " Flux Financier", border=1, fill=True, align="L")
    pdf.cell(40, 8, "Proportion (%)", border=1, fill=True, align="C")
    pdf.cell(40, 8, "Montant (FCFA)", border=1, ln=1, fill=True, align="C")

    montant_cible_lettres = 0

    # ==================== CAS 1 : BON DE PAIEMENT (ACOMPTE SEUL) ====================
    # ==================== CAS 1 : BON DE PAIEMENT (ACOMPTE SEUL) ====================
    if type_document == "bon_paiement" or type_document == "bon_caisse":
        _set_font_safely(pdf, "", 10)
        pdf.cell(110, 7, " Valeur Totale Cacao (Brut)", border=1, align="L")
        pdf.cell(40, 7, "100.0 %", border=1, align="C")
        pdf.cell(40, 7, f"{valeur_brute:,.0f} ", border=1, ln=1, align="R")

        base_calcul = valeur_brute
        if deductions > 0:
            pct_deduct = (deductions / valeur_brute * 100) if valeur_brute > 0 else 0.0
            pdf.set_fill_color(253, 244, 245)
            _set_font_safely(pdf, "I", 10)
            pdf.cell(
                110,
                7,
                f" - {libelle_deductions} (Déduction)",
                border=1,
                fill=True,
                align="L",
            )
            pdf.cell(
                40, 7, f"-{pct_deduct:.1f} %", border=1, fill=True, align="C"
            )
            pdf.cell(
                40, 7, f"-{deductions:,.0f} ", border=1, ln=1, fill=True, align="R"
            )
            base_calcul = valeur_brute - deductions

        pct_avance = (
            (versement / base_calcul * 100) if base_calcul > 0 else 0.0
        )
        pdf.set_fill_color(230, 245, 230)
        _set_font_safely(pdf, "B", 10)
        pdf.cell(
            110,
            8,
            " ACOMPTE VERSÉ CE JOUR (CASH)",
            border=1,
            fill=True,
            align="L",
        )
        pdf.cell(40, 8, f"{pct_avance:.1f} %", border=1, fill=True, align="C")
        pdf.cell(40, 8, f"{versement:,.0f} ", border=1, ln=1, fill=True, align="R")

        montant_cible_lettres = versement

    # ==================== CAS 2 : ENGAGEMENT DE RÈGLEMENT (RESTE A PAYER) ====================
    elif type_document == "engagement_dette":
        _set_font_safely(pdf, "", 10)
        pdf.cell(110, 7, " Valeur Totale Cacao (Brut)", border=1, align="L")
        pdf.cell(40, 7, "100.0 %", border=1, align="C")
        pdf.cell(40, 7, f"{valeur_brute:,.0f} ", border=1, ln=1, align="R")

        net_a_payer = valeur_brute
        if deductions > 0:
            pct_deduct = (
                (deductions / valeur_brute * 100) if valeur_brute > 0 else 0.0
            )
            pdf.set_fill_color(253, 244, 245)
            _set_font_safely(pdf, "I", 10)
            pdf.cell(
                110,
                7,
                f" - {libelle_deductions} (Déduction)",
                border=1,
                fill=True,
                align="L",
            )
            pdf.cell(
                40, 7, f"-{pct_deduct:.1f} %", border=1, fill=True, align="C"
            )
            pdf.cell(
                40, 7, f"-{deductions:,.0f} ", border=1, ln=1, fill=True, align="R"
            )
            net_a_payer = valeur_brute - deductions

        pdf.set_fill_color(245, 245, 245)
        _set_font_safely(pdf, "B", 10)
        pdf.cell(
            110, 7, " VALEUR NETTE COMPTABLE", border=1, fill=True, align="L"
        )
        pdf.cell(
            40,
            7,
            f"{(net_a_payer / valeur_brute * 100):.1f} %",
            border=1,
            fill=True,
            align="C",
        )
        pdf.cell(
            40, 7, f"{net_a_payer:,.0f} ", border=1, ln=1, fill=True, align="R"
        )

        pct_avance = (
            (versement / net_a_payer * 100) if net_a_payer > 0 else 0.0
        )
        _set_font_safely(pdf, "", 10)
        pdf.cell(
            110, 7, " - Acompte versé ce jour (Déduit)", border=1, align="L"
        )
        pdf.cell(40, 7, f"-{pct_avance:.1f} %", border=1, align="C")
        pdf.cell(40, 7, f"-{versement:,.0f} ", border=1, ln=1, align="R")

        reste_a_payer = net_a_payer - versement
        pct_reste = (
            (reste_a_payer / valeur_brute * 100) if valeur_brute > 0 else 0.0
        )
        pdf.set_fill_color(254, 243, 199)
        _set_font_safely(pdf, "B", 11)
        pdf.cell(
            110,
            9,
            " RESTE À PAYER (SOLDE DÛ AU FOURNISSEUR)",
            border=1,
            fill=True,
            align="L",
        )
        pdf.cell(40, 9, f"{pct_reste:.1f} %", border=1, fill=True, align="C")
        pdf.cell(
            40, 9, f"{reste_a_payer:,.0f} ", border=1, ln=1, fill=True, align="R"
        )

        montant_cible_lettres = reste_a_payer

    # ==================== CAS 3 : REÇU DE RÈGLEMENT DE DETTE (APUREMENT) ====================
    elif type_document == "reglement_dette":
        dette_initiale = float(data_paiement.get("dette_initiale", data_paiement.get("reste", 0.0)))
        montant_regle = float(data_paiement.get("montant_regle", data_paiement.get("montant", 0.0)))
        deductions = float(data_paiement.get("deductions", 0.0))
        libelle_deductions = data_paiement.get("libelle_deductions", "Déductions (Transport/Avances)")
    
    # Affichage de la dette initiale
        _set_font_safely(pdf, "", 10)
        pdf.cell(110, 7, " Dette Suspendue Initiale", border=1, align="L")
        pdf.cell(40, 7, "100.0 %", border=1, align="C")
        pdf.cell(40, 7, f"{dette_initiale:,.0f} ", border=1, ln=1, align="R")
    
        net_dette = dette_initiale
        if deductions > 0:
         pct_deduct = (deductions / dette_initiale * 100) if dette_initiale > 0 else 0.0
         pdf.set_fill_color(253, 244, 245)
         _set_font_safely(pdf, "I", 10)
         pdf.cell(110, 7, f" - {libelle_deductions} (Imputé sur reliquat)", border=1, fill=True, align="L")
         pdf.cell(40, 7, f"-{pct_deduct:.1f} %", border=1, fill=True, align="C")
         pdf.cell(40, 7, f"-{deductions:,.0f} ", border=1, ln=1, fill=True, align="R")
         net_dette = dette_initiale - deductions

        pct_versement = (montant_regle / net_dette * 100) if net_dette > 0 else 0.0
        pdf.set_fill_color(230, 245, 230)
        _set_font_safely(pdf, "B", 10)
        pdf.cell(110, 8, " VERSEMENT EFFECTUÉ CE JOUR", border=1, fill=True, align="L")
        pdf.cell(40, 8, f"{pct_versement:.1f} %", border=1, fill=True, align="C")
        pdf.cell(40, 8, f"{montant_regle:,.0f} ", border=1, ln=1, fill=True, align="R")
    
        nouveau_reste = net_dette - montant_regle
        pct_nouveau_reste = (nouveau_reste / dette_initiale * 100) if dette_initiale > 0 else 0.0
        pdf.set_fill_color(250, 240, 240)
        _set_font_safely(pdf, "B", 10)
        pdf.cell(110, 8, " NOUVEAU RESTE À PAYER (SOLDE FINAL)", border=1, fill=True, align="L")
        pdf.cell(40, 8, f"{pct_nouveau_reste:.1f} %", border=1, fill=True, align="C")
        pdf.cell(40, 8, f"{nouveau_reste:,.0f} ", border=1, ln=1, fill=True, align="R")
    
        montant_cible_lettres = montant_regle

    pdf.ln(6)

    # 5. ZONE DE TEXTE (MONTANT EN LETTRES COMPLET ET PROPRE)
    _set_font_safely(pdf, "B", 10)

    if type_document == "engagement_dette":
        phrase_arrete = "Somme restant due arrêtée en toutes lettres : "
    else:
        phrase_arrete = "Montant décaissé arrêté en toutes lettres : "

    pdf.write(6, _clean_text(phrase_arrete))
    _set_font_safely(pdf, "I", 10)

    try:
        from num2words import num2words

        montant_lettres = f"{num2words(int(montant_cible_lettres), lang='fr').capitalize()} FCFA"
    except ImportError:
        montant_lettres = "__________________________________________________"

    pdf.write(6, _clean_text(f"{montant_lettres}\n"))

    _set_font_safely(pdf, "B", 10)
    pdf.write(6, _clean_text("Mode de règlement : "))
    _set_font_safely(pdf, "", 10)
    mode_regl = data_paiement.get(
        "mode_reglement", "Espèces / Virement Bancaire"
    )
    pdf.write(6, _clean_text(f"{mode_regl}\n"))
    pdf.ln(5)

    # 6. BLOC DE SIGNATURES ADAPTÉ
    if pdf.get_y() > 220:
        pdf.add_page()

    _set_font_safely(pdf, "B", 10)
    y_signatures = pdf.get_y()


    # Signature droite (Fournisseur / Direction)
    pdf.set_y(y_signatures)
    pdf.set_x(110)

    if type_document == "engagement_dette":
        pdf.multi_cell(
            90,
            5,
            "Le Fournisseur,\n(Lu et Approuvé pour accord du"
            " Solde)\n\n\n\n\n___________________________\nNom, Signature &"
            " Date",
            align="C",
        )
    else:
        titre_signataire = (
            signataire
            if "signataire" in locals() and signataire
            else ("DG", "DGD")
        )
        pdf.multi_cell(
            90,
            5,
            f"Pour la Direction Générale,\n{titre_signataire}\n\n\n\n\n___________________________\nNom"
            " & Signature / Visa",
            align="C",
        )

        # Insertion dynamique du cachet
        cachet_blob = data_paiement.get("fichier_cachet") or cachet_blob
        if "cachet_blob" in locals() and cachet_blob:
            try:
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".png"
                ) as tmp_file:
                    tmp_file.write(cachet_blob)
                    tmp_path = tmp_file.name

                pdf.image(tmp_path, x=130.5, y=y_signatures + 12, w=65)
                os.remove(tmp_path)
            except Exception as e:
                print(f"Erreur lors du placement du cachet dans le PDF : {e}")

    
    noms_fichiers = {
        "bon_paiement": f"Bon_Acompte_{num_bon}.pdf",
        "engagement_dette": f"Engagement_Solde_{num_bon}.pdf",
        "reglement_dette": f"Recu_Reglement_Dette_{num_bon}.pdf",
    }
    filename = noms_fichiers.get(type_document, f"Document_{num_bon}.pdf")
    pdf.output(filename)

    # --- AJOUT POUR CORRIGER L'APERÇU ---
    # On lit le fichier généré pour extraire les bytes
    with open(filename, "rb") as f:
        pdf_bytes = f.read()

    # On retourne un tuple contenant le nom ET le binaire
    return filename, pdf_bytes

import os
import tempfile
import qrcode
# Assurez-vous d'avoir importé _clean_text et ContratPDF dans votre fichier

def generer_contrat_pdf(
    data_contrat,
    type_document="contrat",
    signataire=("DG", "DGD"),
    cachet_blob=None,
):
    pdf = ContratPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=30)

    # 1. LOGO FCC (Haut Gauche)
    try:
        pdf.image("Logo-FCC.png", x=10, y=5, w=65)
    except FileNotFoundError:
        pass

    # 2. QR CODE D'AUTHENTICITÉ (Haut Droite - Si disponible)
    code_verif = data_contrat.get("code_verification") or data_contrat.get("code_verif")
    if code_verif:
        try:
            # Génération du QR code en image temporaire
            qr_data = f"Ref: {data_contrat.get('num', '')} | Code: {code_verif}"
            qr = qrcode.QRCode(box_size=4, border=1)
            qr.add_data(qr_data)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_qr:
                qr_img.save(tmp_qr.name)
                tmp_qr_path = tmp_qr.name
            # Affichage du QR code (Coin supérieur droit : x=165, y=8, largeur=28mm)
            pdf.image(tmp_qr_path, x=165, y=8, w=28)
            # Mention du code sous le QR Code
            pdf.set_xy(155, 37)
            pdf.set_font("Times", "B", 8)
            pdf.cell(48, 4, _clean_text(f"Code : {code_verif}"), align="C")
            os.remove(tmp_qr_path)
        except Exception as e:
            print(f"Erreur d'insertion du QR Code : {e}")

    # 3. EN-TÊTE DU CONTRAT
    pdf.set_y(38)
    pdf.set_font("Times", "B", 14)
    pdf.cell(
        0,
        8,
        "CONTRAT D'ACHAT CACAO / PURCHASE CONTRACT FOR COCOA",
        ln=1,
        align="C",
    )
    pdf.set_font("Times", "B", 12)
    pdf.cell(
        0,
        8,
        _clean_text(
            f"N° {data_contrat.get('num', '______')} | Date :"
            f" {data_contrat.get('date', '______')}"
        ),
        ln=1,
        align="C",
    )
    pdf.ln(4)
    pdf.set_draw_color(150, 150, 150)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    # 4. INFORMATIONS FOURNISSEUR & CONTRAT
    pdf.set_font("Times", "B", 12)
    pdf.cell(0, 6, "CONDITIONS ET TERMES DU CONTRAT", ln=1)
    pdf.ln(3)
    infos = [
        ("Nom du fournisseur", data_contrat.get("fournisseur", "")),
        (
            "Téléphone & Adresse",
            f"{data_contrat.get('telephone', 'N/A')} |"
            f" {data_contrat.get('ville', '')} - {data_contrat.get('adresse', '')}",
        ),
        (
            "NUI / RCCM",
            f"{data_contrat.get('nui', 'N/A')} /"
            f" {data_contrat.get('rccm', 'N/A')}",
        ),
        (
            "Compte Bancaire",
            data_contrat.get("compte") or data_contrat.get("numero_de_compte") or "N/A",
        ),
        ("Lieu de livraison", data_contrat.get("lieu", "")),
        ("Quantite", f"{data_contrat.get('qte', '')} kg"),
        ("Prix au kg", f"{data_contrat.get('pu', '')} FCFA"),
        ("Delai de livraison", data_contrat.get("delai", "")),
        ("Provenance", data_contrat.get("provenance", "")),
        (
            "Termes de Paiement",
            data_contrat.get("termes_de_paiement", data_contrat.get("termes", "")),
        ),
    ]
    for label, valeur in infos:
        pdf.set_font("Times", "B", 10)
        pdf.cell(40, 6, _clean_text(label), ln=0)
        pdf.set_font("Times", "", 10)
        pdf.cell(0, 6, _clean_text(f": {valeur}"), ln=1)
    pdf.ln(6)

    # 5. SPÉCIFICATIONS DE QUALITÉ
    pdf.set_font("Times", "B", 11)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(60, 7, "Specifications de qualite", border=1, fill=True)
    pdf.cell(55, 7, "Normes / Seuils admis", border=1, ln=1, fill=True)
    pdf.set_font("Times", "", 10)
    specs = [
        ("Taux humidite max", "8% -REF(Si>8%) Volume brut/0,92"),
        ("Dechets", "1.5%"),
        ("Moisissures", "7%"),
        ("Ardoises", "7%"),
        ("Autres defauts", "2,5%"),
        ("Feves plates", "0,5%"),
        ("Matieres etrangeres", "0,5%"),
        ("Non fume", "Obligatoire"),
    ]
    for s, v in specs:
        pdf.cell(60, 6, _clean_text(s), border=1)
        pdf.cell(55, 6, _clean_text(v), border=1, ln=1)
    pdf.ln(6)

    # 6. CLAUSES ET CONDITIONS
    pdf.set_font("Times", "B", 11)
    pdf.cell(0, 6, "Clauses et Conditions Generales :", ln=1)
    pdf.ln(2)
    pdf.set_font("Times", "", 10)
    clauses = [
        (
            "1- La livraison est validee uniquement par le bordereau de l'usine"
            " a l'entree effective du produit en magasin. Ce bon detaille la"
            " qualite, la quantite et l'analyse du produit. Ce bordereau"
            " d'entree est etabli en presence du fournisseur, de maniere"
            " contradictoire et ne peut donc pas etre conteste par la suite."
        ),
        (
            "2- L'acheteur ne maintiendra pas le prix et les conditions du"
            " present contrat au-dela du delai de livraison maximum stipule"
            " dans le present contrat. Au-dela de ce delai de livraison,"
            " l'acheteur aura le droit de reviser le prix et les conditions du"
            " present contrat."
        ),
        (
            "3- Lorsque le fournisseur livre moins de cacao que la quantite"
            " specifiee sur le present contrat, et si le delai maximum est"
            " depasse, l'acheteur aura le droit de reviser le prix et les"
            " conditions du present contrat pour la quantite de cacao restante"
            " a livrer."
        ),
        (
            "4- Le fournisseur doit livrer 100% du cacao specifie dans le"
            " present contrat +/-3%."
        ),
        (
            "5- Le fournisseur s'engage a respecter tous les termes du"
            " contrat. Dans le cas contraire, il en sera tenu pleinement"
            " responsable."
        ),
        (
            "6- L'acheteur fournira au fournisseur un exemplaire du present"
            " contrat."
        ),
        (
            "7- Si le taux d'humidite depasse les 8%, une refraction sur le"
            " prix sera appliquee."
        ),
        (
            "8- Si les autres defauts sont superieurs aux specifications de"
            " qualite, une decote sera appliquee sur le prix. Cette decote est"
            " cumulative (Voir bareme de decote ci-dessous)."
        ),
        (
            "9- En cas de litige, seules les juridictions de Douala seront"
            " competentes."
        ),
        (
            "10- Les paiements seront effectués dans un compte bancaire que"
            " le fournisseur transmettra dans les (04 jours) ouvrables dès"
            " delivrance du bordereau de reception et d'analyse du produit."
        ),
    ]
    
    # CORRECTION 1 : L'indentation a été corrigée pour être DANS la boucle.
    for clause in clauses:
        texte_clause = _clean_text(clause)
        # Estimation du nombre de lignes que va occuper la clause
        nb_lignes = pdf.multi_cell(0, 5, texte_clause, align="J", dry_run=True, output="LINES")
        hauteur_estimee = len(nb_lignes) * 5 + 2  # +2 pour le pdf.ln(2) qui suit

        # Si le bloc ne rentre pas dans l'espace restant avant la marge de bas de page, on saute
        if pdf.get_y() + hauteur_estimee > (pdf.h - pdf.b_margin):
            pdf.add_page()

        pdf.multi_cell(0, 5, texte_clause, align="J")
        pdf.ln(2)
    
    pdf.set_font("Times", "B", 10)
    pdf.cell(0, 6, "Le signataire du present contrat declare :", ln=1)
    pdf.set_font("Times", "I", 10)
    pdf.multi_cell(
        0,
        5,
        _clean_text(
            "- Au moment du depot en magasin, il a la pleine propriete des"
            " produits, qu'ils sont libres et resteront libres de tout"
            " engagement."
        ),
        align="J",
    )
    pdf.ln(1)

    pdf.set_font("Times", "", 10)
    pdf.write(
        5,
        _clean_text(
            "- Il accepte irrevocablement le transfert de propriete de produit,"
            " au profit de "
        ),
    )
    pdf.set_font("Times", "B", 10)
    pdf.write(5, "FRIENDS CAMEROON COMMODITIES")
    pdf.set_font("Times", "", 10)
    pdf.write(5, _clean_text(", des son entree en magasin.\n"))
    pdf.write(
        5,
        _clean_text(
            "- Le signataire du present contrat accepte irrevocablement le"
            " transfert de propriete de produit au profit de "
        ),
    )
    pdf.set_font("Times", "B", 10)
    pdf.write(5, "FRIENDS CAMEROON COMMODITIES")
    pdf.set_font("Times", "", 10)
    pdf.write(5, ".\n")
    pdf.ln(2)

    pdf.set_font("Times", "", 10)
    pdf.multi_cell(
        0,
        5,
        _clean_text(
            "- Le prix du present contrat ne pourra en aucun cas etre modifie"
            " par le fournisseur quel que soit l'evolution du marche.\n-"
            " Le fournisseur comprend et accepte irrevocablement l'ensemble"
            " des conditions et termes du present contrat."
        ),
        align="J",
    )
    pdf.ln(6)

    pdf.set_font("Times", "BU", 11)
    pdf.cell(
        0, 6, "Bareme de decote sur prix pour ardoises et/ou moisis :", ln=1
    )
    pdf.ln(2)
    pdf.set_font("Times", "", 10)
    bareme = (
        "- De 10 a 12% = 10F ; Au-dela de 12%, le cacao est systematiquement"
        " rejete.\n- Si le fournisseur souhaite recuperer son cacao = frais de"
        " dechargement + analyses + rechargement = 20F/Kg Poids Net.\n- Ces"
        " tarifs sont fermes, definis et strictement non negociables."
    )
    pdf.multi_cell(0, 5, _clean_text(bareme), align="J")
    pdf.ln(10)

    # 7. ZONE DE SIGNATURE ET CACHETS
    if pdf.get_y() > 200:
        pdf.add_page()
    pdf.set_font("Times", "B", 10)
    y_signatures = pdf.get_y() + 8

    # ====== PARTIE ACHETEUR (GAUCHE) ======
    pdf.set_xy(10, y_signatures)
    pdf.multi_cell(
        90,
        5,
        _clean_text("Pour l'Acheteur,\nFRIENDS CAMEROON COMMODITIES"),
        align="C",
    )
    # Position du cachet juste sous le nom de la société
    y_cachet = pdf.get_y() + 3
    fichier_cachet = cachet_blob or data_contrat.get("fichier_cachet")
    hauteur_cachet = 0
    
    if fichier_cachet:
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_file:
                tmp_file.write(fichier_cachet)
                tmp_path = tmp_file.name
            # Largeur 52 mm, centré sur la colonne (x = 10 + (90-52)/2 ≈ 29)
            pdf.image(tmp_path, x=29, y=y_cachet, w=52)
            os.remove(tmp_path)
            # Hauteur approximative du cachet (52 mm de large → ~28-32 mm de haut)
            hauteur_cachet = 30
        except Exception as e:
            print(f"Erreur cachet : {e}")

    # ====== PARTIE FOURNISSEUR (DROITE) ======
    pdf.set_xy(110, y_signatures)
    pdf.set_font("Times", "B", 10)
    nom_fournisseur = data_contrat.get("fournisseur", "Le Fournisseur")
    pdf.multi_cell(
        90,
        5,
        _clean_text(f"Pour le Fournisseur,\n{nom_fournisseur}"),
        align="C",
    )

    # CORRECTION 2 : ALIGNEMENT DYNAMIQUE IDENTIQUE
    # On calcule la ligne la plus basse requise (avec ou sans cachet) pour aligner les deux signatures au même niveau.
    y_ligne_commune = max(y_signatures + 15, y_cachet + hauteur_cachet + 2)

    # --- Ligne Acheteur (Gauche) ---
    pdf.set_xy(10, y_ligne_commune)
    pdf.set_font("Times", "B", 10)
    pdf.cell(90, 6, "___________________________", align="C", ln=1)
    pdf.set_x(10)
    pdf.set_font("Times", "", 8)
    pdf.cell(90, 4, "Nom, Signature & Cachet", align="C")

    # --- Ligne Fournisseur (Droite) ---
    pdf.set_xy(110, y_ligne_commune)
    pdf.set_font("Times", "B", 10)
    pdf.cell(90, 6, "___________________________", align="C", ln=1)
    pdf.set_x(110)
    pdf.set_font("Times", "", 8)
    pdf.cell(90, 4, "Nom & Signature", align="C")

    return bytes(pdf.output())

def regenerer_contrat(row_id):
    """Récupère un contrat par son ID en BDD et génère le fichier PDF avec son statut et son cachet."""
    query = """
        SELECT 
            c.numero_contrat, c.date_signature, f.nom AS fournisseur,
            c.lieu_livraison, c.quantite_prevue, c.prix_unitaire,
            c.delai_livraison, c.provenance, c.termes_de_paiement,
            c.statut, c.signataire,
            f.telephone, f.ville, f.adresse, f.Rccm, f.NUI, f.numero_de_compte
        FROM contrats c
        JOIN fournisseurs f ON c.id_fournisseur = f.id
        WHERE c.id = %s
    """
    # Remplacer cursor.execute par fetch_one
    data = fetch_one(query, (row_id,))
    if not data:
        return None

    statut = data[9] if data[9] else "EN_ATTENTE"
    signataire = data[10] if len(data) > 10 and data[10] else None

    fichier_cachet = None

    if statut == "VALIDE":
        if signataire:
            # Utiliser fetch_one
            res_cachet = fetch_one("""
                SELECT fichier_cachet
                FROM cachets_direction
                WHERE role_signataire = %s
                LIMIT 1
            """, (signataire,))
        else:
            # Utiliser fetch_one
            res_cachet = fetch_one("""
                SELECT fichier_cachet
                FROM cachets_direction
                WHERE role_signataire IN ('DG', 'DGD')
                LIMIT 1
            """)
        if res_cachet:
            fichier_cachet = res_cachet[0]

    data_pour_pdf = {
        "num": data[0],
        "date": data[1],
        "fournisseur": data[2],
        "lieu": data[3],
        "qte": data[4],
        "pu": data[5],
        "delai": data[6],
        "provenance": data[7],
        "termes_de_paiement": data[8],
        "statut": statut,
        "signataire": signataire,
        "fichier_cachet": fichier_cachet,
        "telephone": data[11] or "N/A",
        "ville": data[12] or "N/A",
        "adresse": data[13] or "N/A",
        "rccm": data[14] or "N/A",
        "nui": data[15] or "N/A",
        "compte": data[16] or "N/A"
    }

    try:
        return generer_contrat_pdf(data_pour_pdf)
    except Exception as e:
        logging.error(f"Erreur lors de la génération du contrat PDF : {e}")
        return None
    
def fmt_number(val, suffix="KG"):
    """Formate un nombre proprement avec séparateur de milliers."""
    try:
        return f"{float(val):,.2f} {suffix}".replace(",", " ").replace(".00", "")
    except (ValueError, TypeError):
        return f"{val} {suffix}".strip()

class BonReceptionPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='L', unit='mm', format='A4')
        
    def footer(self):
        self.set_y(-45)
        if os.path.exists("Footer-FCC.png"):
            try:
                self.image("Footer-FCC.png", x=15, y=self.get_y(), w=200)
                return
            except Exception:
                pass
        _set_font_safely(self, "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, _clean_text("Document généré automatiquement — Friends Cameroon Commodities"), align="C")


def generer_bon_reception_pdf(data, filename=None):
    num_br = data.get('num_br', 'BR-TEMP')
    if not filename:
        filename = os.path.join(tempfile.gettempdir(), f"Bon_Reception_{num_br}.pdf")
        
    pdf = BonReceptionPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=35)
    pdf.set_margins(15, 15, 15)
    
    C_PRIMARY = (30, 41, 59)
    C_SECONDARY = (71, 85, 105)
    C_BG_LIGHT = (248, 250, 252)
    C_BORDER = (226, 232, 240)
    C_TEXT = (15, 23, 42)
    
    # 1. EN-TÊTE
    pdf.set_fill_color(*C_PRIMARY)
    pdf.rect(190, 15, 92, 28, 'F')
    
    pdf.set_xy(190, 18)
    _set_font_safely(pdf, "B", 12)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(92, 6, _clean_text("BON DE RÉCEPTION"), ln=1, align="C")
    
    _set_font_safely(pdf, "B", 11)
    pdf.set_x(190)
    pdf.cell(92, 6, _clean_text(f"N° {num_br}"), ln=1, align="C")
    
    _set_font_safely(pdf, "", 9)
    pdf.set_x(190)
    pdf.cell(92, 5, _clean_text(f"Date : {data.get('date', 'N/A')}"), ln=1, align="C")
    
    # Logo & Coordonnées (Gauche)
    logo_path = "Logo-FCC.png"
    if os.path.exists(logo_path):
        try:
            pdf.image(logo_path, x=15, y=12, w=70)
            pdf.set_y(38)
        except Exception:
            pdf.set_y(15)
    else:
        pdf.set_y(25)
    
    pdf.ln(12)
    
    def draw_section_header(title):
        pdf.ln(4)
        pdf.set_fill_color(*C_BG_LIGHT)
        pdf.set_draw_color(*C_PRIMARY)
        pdf.set_text_color(*C_PRIMARY)
        _set_font_safely(pdf, "B", 10)
        pdf.cell(267, 8, _clean_text(f"  {title}"), border="B", fill=True, ln=1)
        pdf.ln(3)
        
    def draw_grid_row(label1, val1, label2=None, val2=None):
        _set_font_safely(pdf, "B", 9)
        pdf.set_text_color(*C_TEXT)

        if label2 is None and val2 is None:
            pdf.cell(50, 8, _clean_text(label1), ln=0)

            _set_font_safely(pdf, "", 9)
            pdf.cell(217, 8, _clean_text(str(val1)), ln=1)

        else:
            pdf.cell(50, 8, _clean_text(label1), ln=0)

            _set_font_safely(pdf, "", 9)
            pdf.cell(83, 8, _clean_text(str(val1)), ln=0)

            _set_font_safely(pdf, "B", 9)
            pdf.cell(50, 8, _clean_text(label2), ln=0)

            _set_font_safely(pdf, "", 9)
            pdf.cell(84, 8, _clean_text(str(val2)), ln=1)

        pdf.set_draw_color(*C_BORDER)
        pdf.line(15, pdf.get_y(), 282, pdf.get_y())

    # 2. SECTIONS DU DOCUMENT
    draw_section_header("INFORMATIONS LOGISTIQUES & CONTRACTUELLES")
    draw_grid_row("MAGASIN DESTINATION :", data.get('magasin', 'N/A'), "FOURNISSEUR :", data.get('fournisseur', 'N/A'))
    draw_grid_row("N° CAMION :", data.get('camion', 'N/A'), "N° CONTRAT LIÉ :", data.get('numero_contrat', 'N/A'))
    draw_grid_row("NOM CHAUFFEUR :", data.get('chauffeur', 'N/A'), "PROVENANCE :", data.get('provenance', 'Non spécifiée'))
    draw_grid_row("POIDS NET DÉCLARÉ :", f"{data.get('poids_net_declarer', 0)} kg", "ECART DE POIDS :", f"{data.get('ecart_de_poids', 0)} kg")
    draw_grid_row("NATURE DU PRODUIT :", data.get('nature_produit', 'N/A'))
    draw_grid_row("CENTRE D'ACHAT :", data.get('centre_achat', 'N/A'))

    draw_section_header("RÉSUMÉ DE LA PESÉE")
    draw_grid_row("N° LOT :", data.get('numero_lot', 'N/A'), "NOMBRE DE SACS :", f"{data.get('sacs', 0)} sacs")
    draw_grid_row("POIDS BRUT CONSTATÉ :", f"{data.get('poids_brut', 0)} kg", "POIDS NET RETENU :", f"{data.get('poids_net', 0)} kg")

    # 3. ZONE SIGNATURES
    pdf.ln(12)
    y_sig = pdf.get_y()
    
    pdf.set_fill_color(*C_BG_LIGHT)
    pdf.set_draw_color(*C_BORDER)
    pdf.rect(30, y_sig, 95, 30, 'DF')
    pdf.set_xy(30, y_sig + 3)
    _set_font_safely(pdf, "B", 9)
    pdf.set_text_color(*C_PRIMARY)
    pdf.cell(95, 5, _clean_text("VISA & SIGNATURE TRANSPORTEUR"), ln=1, align="C")
    
    pdf.set_xy(172, y_sig)
    pdf.rect(172, y_sig, 95, 30, 'DF')
    pdf.set_xy(172, y_sig + 3)
    pdf.cell(95, 5, _clean_text("CACHET & SIGNATURE MAGASINIER"), ln=1, align="C")

    pdf.output(filename)
    return filename

# =====================================================================
# --- GENERATEUR 2 : BORDEREAU DE LIVRAISON (BL) - FPDF (PAYSAGE)
# =====================================================================

class BordereauLivraisonPDF(FPDF):
    def __init__(self):
        super().__init__(orientation='L', unit='mm', format='A4')
    def footer(self):
        self.set_y(-45) # Ajusté pour laisser de la place
        if os.path.exists("Footer-FCC.png"):
            try:
                self.image("Footer-FCC.png", x=15, y=self.get_y(), w=227)
                return
            except Exception:
                pass
        _set_font_safely(self, "I", 8)
        self.set_text_color(148, 163, 184)
        self.cell(0, 10, _clean_text("Document généré automatiquement — Friends Cameroon Commodities"), align="C")


def generer_bordereau_livraison_pdf(data_bl, filename=None):
    num_bl = data_bl.get('num_bl', 'BL-TEMP')
    if not filename:
        filename = os.path.join(tempfile.gettempdir(), f"BL_{num_bl}.pdf")
        
    pdf = BordereauLivraisonPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=35)
    pdf.set_margins(15, 15, 15)
    
    C_PRIMARY = (30, 41, 59)
    C_SECONDARY = (71, 85, 105)
    C_BG_LIGHT = (248, 250, 252)
    C_BORDER = (226, 232, 240)
    C_TEXT = (15, 23, 42)
    
    # 1. EN-TÊTE
    pdf.set_fill_color(*C_PRIMARY)
    pdf.rect(190, 15, 92, 28, 'F')
    
    pdf.set_xy(190, 18)
    _set_font_safely(pdf, "B", 12)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(92, 6, _clean_text("BORDEREAU DE LIVRAISON"), ln=1, align="C")
    
    _set_font_safely(pdf, "B", 11)
    pdf.set_x(190)
    pdf.cell(92, 6, _clean_text(f"N° {num_bl}"), ln=1, align="C")
    
    _set_font_safely(pdf, "", 9)
    pdf.set_x(190)
    pdf.cell(92, 5, _clean_text(f"Date : {data_bl.get('date', 'N/A')}"), ln=1, align="C")
    
    # Logo & Coordonnées (Gauche)
    logo_path = "Logo-FCC.png"
    if os.path.exists(logo_path):
        try:
            # w augmenté à 70. FPDF calcule la hauteur automatiquement pour ne pas déformer
            pdf.image(logo_path, x=15, y=12, w=70)
            pdf.set_y(38)
        except Exception:
            pdf.set_y(15)
    else:
        pdf.set_y(25)
            
    pdf.ln(12)
    
    def draw_section_header(title):
        pdf.ln(4)
        pdf.set_fill_color(*C_BG_LIGHT)
        pdf.set_draw_color(*C_PRIMARY)
        pdf.set_text_color(*C_PRIMARY)
        _set_font_safely(pdf, "B", 10)
        pdf.cell(267, 8, _clean_text(f"  {title}"), border="B", fill=True, ln=1)
        pdf.ln(3)
        
    def draw_grid_row(label1, val1, label2, val2):
        _set_font_safely(pdf, "B", 9)
        pdf.set_text_color(*C_TEXT)
        pdf.cell(50, 8, _clean_text(label1), ln=0)
        
        _set_font_safely(pdf, "", 9)
        pdf.cell(83, 8, _clean_text(str(val1)), ln=0)
        
        _set_font_safely(pdf, "B", 9)
        pdf.cell(50, 8, _clean_text(label2), ln=0)
        
        _set_font_safely(pdf, "", 9)
        pdf.cell(84, 8, _clean_text(str(val2)), ln=1)
        
        pdf.set_draw_color(*C_BORDER)
        pdf.line(15, pdf.get_y(), 282, pdf.get_y())

    # 2. SECTIONS DU DOCUMENT
    draw_section_header("CARACTÉRISTIQUES DE LA MARCHANDISE")
    draw_grid_row("PRODUIT / NATURE :", data_bl.get('nature', 'CACAO GRADE 1'), "NOMBRE DE SACS :", f"{data_bl.get('sacs', 0)} sacs")
    draw_grid_row("POIDS NET SORTI :", f"{data_bl.get('poids_net', 0)} kg", "MAGASIN DÉPART :", data_bl.get('magasin_depart', 'N/A'))
    draw_grid_row("TAUX HUMIDITÉ :", f"{data_bl.get('taux_humidite', 0)} %", "TAUX MOISISSURE :", f"{data_bl.get('taux_moisissure', 0)} %")
    
    draw_section_header("DESTINATION & LOGISTIQUE")
    draw_grid_row("DESTINATAIRE :", data_bl.get('destination', 'N/A'), "N° CAMION :", data_bl.get('camion', 'N/A'))
    draw_grid_row("NOM CHAUFFEUR :", data_bl.get('chauffeur', 'N/A'), "DATE D'EXPÉDITION :", data_bl.get('date', 'N/A'))

    # 3. ZONE SIGNATURES
    pdf.ln(12)
    y_sig = pdf.get_y()
    
    pdf.set_fill_color(*C_BG_LIGHT)
    pdf.set_draw_color(*C_BORDER)
    pdf.rect(30, y_sig, 95, 30, 'DF')
    pdf.set_xy(30, y_sig + 3)
    _set_font_safely(pdf, "B", 9)
    pdf.set_text_color(*C_PRIMARY)
    pdf.cell(95, 5, _clean_text("SIGNATURE TRANSPORTEUR / CHAUFFEUR"), ln=1, align="C")
    
    pdf.set_xy(172, y_sig)
    pdf.rect(172, y_sig, 95, 30, 'DF')
    pdf.set_xy(172, y_sig + 3)
    pdf.cell(95, 5, _clean_text("VISA / CACHET RESPONSABLE MAGASIN"), ln=1, align="C")

    pdf.output(filename)
    return filename

import os
import tempfile
import qrcode
from fpdf import FPDF
import logging

class BulletinAnalysePDF(FPDF):
    def footer(self):
        self.set_y(-25)
        if os.path.exists("Footer-FCC.png"):
            try:
                self.image("Footer-FCC.png", x=10, y=self.get_y(), w=165)
            except Exception as e:
                logging.error(f"Erreur footer : {e}")
        else:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(120, 120, 120)
            self.cell(0, 10, "Document officiel d'analyse qualité - FCC", align="C")

def _clean(text):
    """Nettoie le texte pour éviter les erreurs d'encodage FPDF standard."""
    return str(text).encode('latin-1', 'replace').decode('latin-1')

def generer_bulletin_analyse_cacao_pdf(data, filename="Bulletin_Analyse_Cacao.pdf"):
    pdf = BulletinAnalysePDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=30)
    
    # ---- EN-TÊTE ----
    if os.path.exists("Logo-FCC.png"):
        try:
            pdf.image("Logo-FCC.png", x=10, y=8, w=35)
        except Exception as e:
            logging.error(f"Erreur logo : {e}")
            
    type_b = data.get("type_bulletin") or "Tout Venant (TV)"
    titre_pdf = "BULLETIN D'ANALYSE EXPORT" if "Export" in str(type_b) else "BULLETIN D'ANALYSE TOUT VENANT (TV)"
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_xy(50, 12)
    pdf.cell(110, 10, _clean(titre_pdf), border=1, ln=1, align="C")
    
    # ---- 1. INFORMATIONS GÉNÉRALES RÉCEPTION ----
    pdf.set_y(32)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(230, 230, 230)
    pdf.cell(190, 6, _clean(" 1. INFORMATIONS DE LA RÉCEPTION & ÉCHANTILLON"), border=1, ln=1, fill=True)
    
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(95, 6, _clean(f" N° Bulletin : {data.get('numero_br')}"), border="L-R-B")
    poids_brut_val = data.get('poids_brut_receptionne') or 0
    pdf.cell(95, 6, _clean(f" Poids Brut Réceptionné : {poids_brut_val:,.2f} Kg"), border="R-B", ln=1)
    poids_net_rec = data.get('poids_net_reception') or poids_brut_val
    pdf.cell(95, 6, _clean(f" Poids Net Réception : {poids_net_rec:,.2f} Kg"), border="L-R-B")
    pdf.cell(95, 6, _clean(f" Échantillon Analysé : {data.get('poids_total', 0) or 0:,.2f} g"), border="R-B", ln=1)
    if data.get("numero_lot") or data.get("fournisseur"):
        pdf.cell(95, 6, _clean(f" Lot : {data.get('numero_lot', 'N/A')}"), border="L-R-B")
        pdf.cell(95, 6, _clean(f" Fournisseur : {data.get('fournisseur', 'N/A')}"), border="R-B", ln=1)
    
    pdf.ln(4)

    # ---- 2. TAMISAGE, FÈVES PLATES & CORPS ÉTRANGERS ----
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 6, _clean(" 2. TAMISAGE, FÈVES PLATES & CORPS ÉTRANGERS"), border=1, ln=1, fill=True)
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(80, 5, _clean("Élément"), border=1, align="C")
    pdf.cell(55, 5, _clean("Poids (g)"), border=1, align="C")
    pdf.cell(55, 5, _clean("Taux (%)"), border=1, ln=1, align="C")
    
    pdf.set_font("Helvetica", "", 8)
    items_tami = [
        ("Débris Tamisage", data.get('p_debris'), data.get('t_debris')),
        ("Fèves Plates", data.get('p_plates'), data.get('t_plates')),
        ("Corps Étrangers", data.get('p_etrangers'), data.get('t_etrangers'))
    ]
    for nom, p, t in items_tami:
        pdf.cell(80, 5, _clean(f" {nom}"), border=1)
        pdf.cell(55, 5, f"{(p or 0):.2f} g", border=1, align="C")
        pdf.cell(55, 5, f"{(t or 0):.2f} %", border=1, ln=1, align="C")

    pdf.ln(4)

    # ---- 3. MATIÈRE DÉRIVÉE DU CACAO (MDC) ----
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 6, _clean(" 3. MATIÈRE DÉRIVÉE DU CACAO (MDC)"), border=1, ln=1, fill=True)
    
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(95, 5, _clean("Composante"), border=1, align="C")
    pdf.cell(95, 5, _clean("Poids (g)"), border=1, ln=1, align="C")
    
    pdf.set_font("Helvetica", "", 8)
    items_mdc = [
        ("Crabots", data.get('p_crabots')),
        ("Fèves Brisées", data.get('p_brisees')),
        ("Fragments / Coques", data.get('p_frag'))
    ]
    for nom, p in items_mdc:
        pdf.cell(95, 5, _clean(f" {nom}"), border=1)
        pdf.cell(95, 5, f"{(p or 0):.2f} g", border=1, ln=1, align="C")
        
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(95, 5, _clean(" SOUS-TOTAL MDC"), border=1)
    pdf.cell(95, 5, f"{(data.get('st_mdc_poids') or 0):.2f} g  |  {(data.get('st_mdc_taux') or 0):.2f} %", border=1, ln=1, align="C")

    pdf.ln(4)

    # ---- 4. HUMIDITÉ & ÉPREUVE À LA COUPE ----
    # ---- 4. HUMIDITÉ & ÉPREUVE À LA COUPE ----
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(190, 6, _clean(" 4. HUMIDITÉ "), border=1, ln=1, fill=True)

    pdf.set_font("Helvetica", "", 8)
    pdf.cell(63, 5, _clean(f" Taux d'Humidité : {(data.get('humidite') or 0):.1f} %"), border=1)

    pdf.ln(5)

    # ---- 5. ÉPREUVE À LA COUPE (3 x 100 fèves) ----
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(190, 6, _clean(" 5. ÉPREUVE À LA COUPE (3 x 100 fèves)"), border=1, ln=1, fill=True)

    # En-tête du tableau
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(50, 5, _clean("Défaut"), border=1, align="C")
    pdf.cell(30, 5, _clean("C1"), border=1, align="C")
    pdf.cell(30, 5, _clean("C2"), border=1, align="C")
    pdf.cell(30, 5, _clean("C3"), border=1, align="C")
    pdf.cell(50, 5, _clean("Moyenne (%)"), border=1, ln=1, align="C")

    # Données
    defauts_pdf = [
        ("Moisissures", 'moisies_c1', 'moisies_c2', 'moisies_c3', 'pct_moisies'),
        ("Ardoises", 'ardoisees_c1', 'ardoisees_c2', 'ardoisees_c3', 'pct_ardoisees'),
        ("Mitées", 'mitees_c1', 'mitees_c2', 'mitees_c3', 'pct_mitees'),
        ("Germées", 'germees_c1', 'germees_c2', 'germees_c3', 'pct_germees'),
        ("Violettes", 'violettes_c1', 'violettes_c2', 'violettes_c3', 'pct_violettes'),
        ("White spots", 'white_spots_c1', 'white_spots_c2', 'white_spots_c3', 'pct_white_spots'),
    ]

    pdf.set_font("Helvetica", "", 8)
    for label, c1_key, c2_key, c3_key, moy_key in defauts_pdf:
        c1 = data.get(c1_key, 0)
        c2 = data.get(c2_key, 0)
        c3 = data.get(c3_key, 0)
        moy = data.get(moy_key, 0)
        pdf.cell(50, 5, _clean(f" {label}"), border=1)
        pdf.cell(30, 5, f"{c1}", border=1, align="C")
        pdf.cell(30, 5, f"{c2}", border=1, align="C")
        pdf.cell(30, 5, f"{c3}", border=1, align="C")
        pdf.cell(50, 5, f"{moy:.1f} %", border=1, ln=1, align="C")

    # Grainage
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(140, 6, _clean(" GRAINAGE (Nb fèves / 100 g)"), border=1)
    feves_100g = data.get('feves_pour_100g', 0)
    pdf.cell(50, 6, f"{feves_100g:.1f}", border=1, ln=1, align="C")

    if feves_100g > 120:
        pdf.set_text_color(200, 0, 0)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(0, 5, _clean("⚠️ GRAINAGE > 120 → REJET AUTOMATIQUE"), ln=1, align="L")
        pdf.set_text_color(0, 0, 0)

    pdf.ln(6)


    # ---- 6. BILAN DES RÉFRACTIONS (avec coefficient) ----
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(200, 220, 240)
    pdf.cell(190, 6, _clean(f" 6. BILAN DES RÉFRACTIONS (coeff. {data.get('coeff_applique', 0.3)*100:.0f}%)"), border=1, ln=1, fill=True)

    # Poids net réceptionné
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(130, 6, _clean(" Poids Net Réceptionné (base)"), border=1)
    pdf.cell(60, 6, f"{data.get('poids_net_reception', 0):,.2f} Kg", border=1, ln=1, align="R")

    # Liste des réfactions (seulement celles > 0) - critères retenus
    items_ref = [
        ('Humidité', data.get('ref_humidite', 0)),
        ('Débris tamisage', data.get('ref_debris', 0)),
        ('Corps étrangers', data.get('ref_etrangers', 0)),
        ('Fèves plates', data.get('ref_plates', 0)),
        ('MDC (crabots+brisees+frag)', data.get('ref_mdc', 0)),
    ]
    pdf.set_text_color(180, 0, 0)
    for label, val in items_ref:
        if val > 0:
            pdf.cell(130, 6, _clean(f" Réfraction {label}"), border=1)
            pdf.cell(60, 6, f"- {val:,.2f} Kg", border=1, ln=1, align="R")

    # Total des réfractions (en noir)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(130, 6, _clean(" TOTAL RÉFRACTIONS"), border=1)
    pdf.cell(60, 6, f"- {data.get('total_ref', 0):,.2f} Kg", border=1, ln=1, align="R")

    # Poids net payable (vert)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(220, 245, 220)
    pdf.cell(130, 8, _clean(" POIDS NET PAYABLE (BASE DE FACTURATION)"), border=1, fill=True)
    pdf.cell(60, 8, f"{data.get('poids_net_paye', 0):,.2f} Kg", border=1, ln=1, align="R", fill=True)

    # Affichage du plafond si appliqué
    plafond = data.get('plafond_applique', 0)
    if plafond > 0 and data.get('total_ref', 0) == plafond:
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 5, _clean(f"(Plafond de réfaction de {data.get('plafond_pourcentage', 1.0):.1f}% appliqué)"), ln=1)

    # ---- SIGNATURES & CACHET ----
    pdf.ln(8)
    y_sig = pdf.get_y()
    
    # Cadre Analyste / Contrôleur
    pdf.set_xy(10, y_sig)
    pdf.rect(10, y_sig, 85, 30)
    pdf.set_xy(10, y_sig + 2)
    pdf.set_font("Helvetica", "B", 8)
    pdf.cell(85, 4, _clean("VISA & SIGNATURE ANALYSTE"), align="C")

    # Cadre Responsable Qualité / Cachet
    pdf.set_xy(115, y_sig)
    pdf.rect(115, y_sig, 85, 30)
    pdf.set_xy(115, y_sig + 2)
    pdf.cell(85, 4, _clean("CACHET & SIGNATURE RESP. QUALITÉ"), align="C")

    # Insertion Cachet BLOB (si fourni)
    if data.get('fichier_cachet'):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(data.get('fichier_cachet'))
                tmp_path = tmp.name
            pdf.image(tmp_path, x=135, y=y_sig + 7, w=45)
            os.remove(tmp_path)
        except Exception as e:
            logging.error(f"Erreur cachet : {e}")

    # ---- GENERATION QR CODE VERIFICATION ----
    donnees_qr = f"BR:{data.get('numero_br')}|BRUT:{data.get('poids_brut_receptionne')}KG|NET:{data.get('poids_net_paye')}KG"
    try:
        qr = qrcode.QRCode(box_size=3, border=1)
        qr.add_data(donnees_qr)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp_qr:
            qr_img.save(tmp_qr.name)
            tmp_qr_path = tmp_qr.name
            
        pdf.image(tmp_qr_path, x=170, y=8, w=22)
        os.remove(tmp_qr_path)
    except Exception as e:
        logging.error(f"Erreur QR Code : {e}")

    # Exportation finale
    pdf.output(filename)
    with open(filename, "rb") as f:
        pdf_bytes = f.read()

    return filename, pdf_bytes

def determiner_statut_qualite(
    humidite,
    taux_debris,
    taux_etrangers,
    taux_mdc,
    moisies,
    ardoisees,
    grainage,
    contamination="Conforme",
):
    """
    Retourne :
        CONFORME
        REFACTURE
        DECLASSE
        REJETE
    """

    motifs_rejet = []
    motifs_declassement = []
    motifs_refaction = []

    # =========================================================
    # 1. REJET : défauts critiques
    # =========================================================

    if humidite > 12:
        motifs_rejet.append(f"Humidité critique : {humidite:.1f}%")

    if moisies > 12:
        motifs_rejet.append(f"Moisissures critiques : {moisies:.1f}%")

    if ardoisees > 12:
        motifs_rejet.append(f"Ardoisées critiques : {ardoisees:.1f}%")

    if taux_debris > 5:
        motifs_rejet.append(f"Débris critiques : {taux_debris:.2f}%")

    if taux_etrangers > 5:
        motifs_rejet.append(
            f"Corps étrangers critiques : {taux_etrangers:.2f}%"
        )

    if grainage > 120:
        motifs_rejet.append(
            f"Grainage critique : {grainage:.1f} fèves/100g"
        )

    # Contamination dangereuse
    if contamination in ["Fumé/Hammy", "Autre"]:
        motifs_rejet.append(
            f"Contamination organoleptique : {contamination}"
        )

    if motifs_rejet:
        return {
            "statut": "REJETE",
            "motifs": motifs_rejet,
            "niveau": 4
        }

    # =========================================================
    # 2. DÉCLASSEMENT : qualité insuffisante mais cacao
    #    encore commercialisable
    # =========================================================

    if moisies > 7:
        motifs_declassement.append(
            f"Moisissures élevées : {moisies:.1f}%"
        )

    if ardoisees > 7:
        motifs_declassement.append(
            f"Ardoisées élevées : {ardoisees:.1f}%"
        )

    if taux_mdc > 6:
        motifs_declassement.append(
            f"MDC élevée : {taux_mdc:.2f}%"
        )

    if grainage > 100:
        motifs_declassement.append(
            f"Grainage élevé : {grainage:.1f} fèves/100g"
        )

    if motifs_declassement:
        return {
            "statut": "DECLASSE",
            "motifs": motifs_declassement,
            "niveau": 3
        }

    # =========================================================
    # 3. REFACTURATION : dépassement léger des tolérances
    # =========================================================

    if humidite > 8:
        motifs_refaction.append(
            f"Humidité : {humidite:.1f}%"
        )

    if taux_debris > 1.5:
        motifs_refaction.append(
            f"Débris : {taux_debris:.2f}%"
        )

    if taux_etrangers > 0.75:
        motifs_refaction.append(
            f"Corps étrangers : {taux_etrangers:.2f}%"
        )

    if taux_mdc > 3:
        motifs_refaction.append(
            f"MDC : {taux_mdc:.2f}%"
        )

    if motifs_refaction:
        return {
            "statut": "REFACTURE",
            "motifs": motifs_refaction,
            "niveau": 2
        }

    # =========================================================
    # 4. CONFORME
    # =========================================================

    return {
        "statut": "CONFORME",
        "motifs": [],
        "niveau": 1
    }
# ==========================================
# 5. FONCTIONS UTILITAIRES DE DONNÉES
# ==========================================
# ----- Fonctions pour interagir avec PostgreSQL sans SQLAlchemy -----
def get_single_value(query, default=0):
    """Exécute une requête et retourne la première colonne de la première ligne."""
    with conn.cursor() as cur:
        cur.execute(query)
        row = cur.fetchone()
        return row[0] if row and row[0] is not None else default

def fetch_all(query, params=None):
    """Exécute une requête SELECT et retourne toutes les lignes."""
    try:
        with conn.cursor() as cur:

            if params is None:
                cur.execute(query)
            else:
                if not isinstance(params, (tuple, list)):
                    params = (params,)

                cur.execute(query, tuple(params))

            return cur.fetchall()

    except Exception as e:
        logging.error(f"Erreur fetch_all : {e}")
        raise
def fetch_one(query, params=None, default=None):
    """Exécute une requête SELECT et retourne une seule ligne."""
    try:
        with conn.cursor() as cur:

            # Aucun paramètre : surtout ne pas envoyer ()
            # afin que les % SQL de LIKE ne soient pas interprétés
            # comme des placeholders Python.
            if params is None:
                cur.execute(query)
            else:
                if not isinstance(params, (tuple, list)):
                    params = (params,)

                cur.execute(query, tuple(params))

            row = cur.fetchone()
            return row if row is not None else default

    except Exception as e:
        logging.error(f"Erreur fetch_one : {e}")
        raise

def get_dataframe_from_query(query, params=None):
    import pandas as pd
    with conn.cursor() as cur:
        cur.execute(query, params or ())
        rows = cur.fetchall()
        if not rows:
            return pd.DataFrame()
        colnames = [desc[0] for desc in cur.description]
        return pd.DataFrame(rows, columns=colnames)

@st.cache_data(ttl=60)
def get_stock_actuel():
    """Retourne le stock actuel (entrée - sortie) en kg."""
    entree = get_single_value("SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE type = 'Entrée'")
    sortie = get_single_value("SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE type = 'Sortie'")
    return entree - sortie

def insert_dict(cursor, table, data):
    """
    Insère une ligne dans `table` à partir d'un dictionnaire `data` (colonne -> valeur).
    Retourne l'ID inséré si la table a une colonne `id` avec RETURNING, sinon None.
    """
    columns = data.keys()
    values = [data[col] for col in columns]
    placeholders = ', '.join(['%s'] * len(columns))
    cols = ', '.join(columns)
    query = f"INSERT INTO {table} ({cols}) VALUES ({placeholders}) RETURNING id"
    cursor.execute(query, values)
    row = cursor.fetchone()
    return row[0] if row else None

# ==========================================
# 6. MENU LATÉRAL DYNAMIQUE (RBAC)
# ==========================================
with st.sidebar:
    # --- En-tête utilisateur ---
    role_badges = {
        "Admin": "🔴 Administrateur",
        "Direction": "🟣 Direction",
        "Employé": "🟢 Employé"
    }
    badge = role_badges.get(st.session_state.role, f"⚪ {st.session_state.role}")

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #1f2937, #111827);
            border-radius: 12px;
            padding: 14px 16px;
            margin-bottom: 10px;
            border: 1px solid #2d3748;
        ">
            <div style="font-size: 13px; color: #9ca3af; margin-bottom: 4px;">
                Connecté en tant que
            </div>
            <div style="font-size: 16px; font-weight: 700; color: #f9fafb;">
                👤 {st.session_state.username}
            </div>
            <div style="font-size: 12px; color: #d1d5db; margin-top: 6px;">
                {badge}
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if st.button("🚪 Déconnexion", use_container_width=True):
        log_action("Déconnexion")
        st.session_state.logged_in = False
        st.rerun()

    st.divider()

    # --- Liste de référence absolue de TOUS les onglets possibles ---
    ONGLETS_DISPONIBLES = [
        "🏠 Tableau de Bord",
        "📦 Mouvements de Stock",
        "🧾 Achats (Entrees)",
        "🛍️ Ventes (Sorties)",
        "👥 Clients",
        "🤝 Fournisseurs",
        "🏗️ Prestataires & Transitaires",
        "📝 Contrats",
        "🏪 Magasins",
        "👑 Espace Direction",
        "⚙️ Administration & Backup"
    ]

    # --- Récupération des permissions de l'utilisateur connecté ---
    permissions_raw = st.session_state.get("permissions_raw", None)

    if permissions_raw is not None and permissions_raw != "":
        menus_autorises = [m.strip() for m in permissions_raw.split(",") if m.strip()]
        menus = [m for m in menus_autorises if m in ONGLETS_DISPONIBLES]
    else:
        if st.session_state.role == "Admin":
            menus = ONGLETS_DISPONIBLES.copy()
        else:
            menus = [m for m in ONGLETS_DISPONIBLES if m != "⚙️ Administration & Backup"]

    # --- Sécurité ultime : accès minimal garanti ---
    if not menus:
        menus = ["🏠 Tableau de Bord"]

    # --- Titre du menu ---
    st.markdown(
        """
        <div style="
            font-size: 12px;
            font-weight: 700;
            color: #6b7280;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
        ">
            📋 Menu Principal
        </div>
        """,
        unsafe_allow_html=True
    )

    choix = st.radio("Menu Principal", menus, label_visibility="collapsed")

    # --- Pied de sidebar ---
    st.markdown(
        f"""
        <div style="
            margin-top: 24px;
            padding-top: 12px;
            border-top: 1px solid #2d3748;
            font-size: 11px;
            color: #6b7280;
            text-align: center;
        ">
            {len(menus)} module{'s' if len(menus) > 1 else ''} accessible{'s' if len(menus) > 1 else ''}
        </div>
        """,
        unsafe_allow_html=True
    )

# ==========================================
# 7. PAGES DE L'APPLICATION
# ==========================================

import plotly.graph_objects as go

if choix == "🏠 Tableau de Bord":
    # ---------------------------------------------------------
    # 0. INJECTION CSS (Pour sublimer les cartes et l'en-tête)
    # ---------------------------------------------------------
    st.markdown("""
        <style>
            /* Style pour l'en-tête */
            .dashboard-header {
                background: linear-gradient(135deg, #1E293B 0%, #0F172A 100%);
                padding: 1.8rem 2rem;
                border-radius: 16px;
                color: white;
                margin-bottom: 2rem;
                box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1);
            }
            .dashboard-header h1 {
                color: #FFFFFF !important;
                font-weight: 700 !important;
                margin-bottom: 0.2rem !important;
            }
            .dashboard-header p {
                color: #94A3B8 !important;
                font-size: 1.05rem;
                margin: 0;
            }
            /* Style pour la banner de balance */
            .balance-card {
                padding: 1.2rem;
                border-radius: 12px;
                text-align: center;
                font-weight: 600;
                font-size: 1.2rem;
                margin-top: 1rem;
            }
            .balance-positive {
                background-color: #ECFDF5;
                color: #065F46;
                border: 1px solid #A7F3D0;
            }
            .balance-negative {
                background-color: #FEF2F2;
                color: #991B1B;
                border: 1px solid #FECACA;
            }
        </style>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # 1. EN-TÊTE DASHBOARD
    # ---------------------------------------------------------
    st.markdown("""
        <div class="dashboard-header">
            <h1>🏠 Tableau de Bord Général</h1>
            <p>Vue d'ensemble stratégique et analytique en temps réel — <b>Friends Cameroon Commodities</b></p>
        </div>
    """, unsafe_allow_html=True)

    # ---------------------------------------------------------
    # 2. RÉCUPÉRATION DES DONNÉES GLOBALES (AVEC DEVISE)
    # ---------------------------------------------------------
    def get_val(q, default=0):
        with conn.cursor() as cur:
            cur.execute(q)
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else default

    try:
        # --- Achats (toujours en FCFA) ---
        tot_achats = get_val("SELECT COALESCE(SUM(total), 0) FROM achats WHERE statut != 'En attente de facturation'")
        dette_fournisseurs = get_val("SELECT COALESCE(SUM(total - montant_avance), 0) FROM achats WHERE statut != 'En attente de facturation'")
        total_volume_achete = get_val("SELECT COALESCE(SUM(quantite_kg), 0) FROM achats WHERE statut != 'En attente de facturation'")

        # --- Ventes : regrouper par devise ---
        ventes_par_devise = {}
        creances_par_devise = {}
        total_volume_vendu = 0

        with conn.cursor() as cur:
            # Totaux des ventes par devise
            cur.execute("""
                SELECT devise, COALESCE(SUM(total), 0) 
                FROM ventes 
                WHERE statut != 'En attente de facturation' 
                GROUP BY devise
            """)
            for row in cur.fetchall():
                ventes_par_devise[row[0]] = row[1]

            # Créances clients par devise
            cur.execute("""
                SELECT devise, COALESCE(SUM(total), 0) 
                FROM ventes 
                WHERE statut_paiement != 'Payé' 
                GROUP BY devise
            """)
            for row in cur.fetchall():
                creances_par_devise[row[0]] = row[1]

            # Volume total vendu (kg) - pas de devise
            cur.execute("SELECT COALESCE(SUM(quantite_kg), 0) FROM ventes WHERE statut != 'En attente de facturation'")
            total_volume_vendu = cur.fetchone()[0] or 0

        # --- Stock ---
        entree = get_val("SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE type='Entrée'")
        sortie = get_val("SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE type='Sortie'")
        stock_actuel = entree - sortie

        # --- Taux de change (à personnaliser) ---
        TAUX_CHANGE = {
            'XAF': 1.0,
            'EUR': 655.957,   # 1 EUR = 655.957 XAF
            'USD': 600.0,     # Exemple, à ajuster
            'GBP': 750.0,     # Exemple
        }

        # Calcul du total des ventes en FCFA (pour la balance)
        tot_ventes_xaf = 0.0
        for devise, montant in ventes_par_devise.items():
            tot_ventes_xaf += montant * TAUX_CHANGE.get(devise, 1.0)

        benefice_brut = tot_ventes_xaf - tot_achats

    except Exception as e:
        st.error(f"❌ Erreur lors du chargement des données du tableau de bord : {e}")
        st.stop()

    # ---------------------------------------------------------
    # 3. AFFICHAGE DES KPIS (avec devises pour les ventes)
    # ---------------------------------------------------------
    st.markdown("### 💰 Santé Financière")
    with st.container(border=True):
        f1, f2, f3, f4 = st.columns(4)

        # Dépenses (Achats) – toujours en FCFA
        f1.metric("Dépenses (Achats)", f"{tot_achats:,.0f} FCFA".replace(",", " "))

        # Revenus (Ventes) – affichage par devise
        if ventes_par_devise:
            # On construit une chaîne du type "54 000 EUR, 120 000 XAF"
            parts = []
            for devise, montant in sorted(ventes_par_devise.items()):
                parts.append(f"{montant:,.0f} {devise}".replace(",", " "))
            f2.metric("Revenus (Ventes)", ", ".join(parts))
        else:
            f2.metric("Revenus (Ventes)", "0 FCFA")

        # Dette Fournisseurs – toujours en FCFA
        f3.metric("Dette Fournisseurs", f"{dette_fournisseurs:,.0f} FCFA".replace(",", " "), delta="-Engagements", delta_color="inverse")

        # Créances Clients – par devise
        if creances_par_devise:
            parts = []
            for devise, montant in sorted(creances_par_devise.items()):
                parts.append(f"{montant:,.0f} {devise}".replace(",", " "))
            f4.metric("Créances Clients", ", ".join(parts), delta="+À recouvrir", delta_color="normal")
        else:
            f4.metric("Créances Clients", "0 FCFA", delta="+À recouvrir", delta_color="normal")

        # Banner dynamique de la balance commerciale (en FCFA)
        balance_class = "balance-positive" if benefice_brut >= 0 else "balance-negative"
        balance_icon = "📈" if benefice_brut >= 0 else "📉"
        st.markdown(f"""
            <div class="balance-card {balance_class}">
                {balance_icon} Balance Commerciale Brute (en FCFA) : <b>{benefice_brut:,.0f} FCFA</b>
            </div>
        """, unsafe_allow_html=True)

    st.write("") # Espacement

    # --- SECTION LOGISTIQUE & STOCKS (inchangée) ---
    st.markdown("### 📦 Mouvements & Stocks Physiques (Cacao)")
    with st.container(border=True):
        l1, l2, l3 = st.columns(3)
        l1.metric("Total Acheté (Historique)", f"{total_volume_achete:,.0f} kg".replace(",", " "))
        l2.metric("Total Vendu (Historique)", f"{total_volume_vendu:,.0f} kg".replace(",", " "))

        delta_val = total_volume_achete - total_volume_vendu
        l3.metric(
            "Stock Actuel Disponible",
            f"{stock_actuel:,.0f} kg".replace(",", " "),
            delta=f"{delta_val:,.0f} kg (Théorique)".replace(",", " ")
        )

    st.write("")

    # ---------------------------------------------------------
    # 4. GRAPHIQUE PROFESSIONNEL (PLOTLY) – FLUX ACHATS / VENTES
    # ---------------------------------------------------------
    st.markdown("### 📊 Évolution Temporelle des Flux (kg)")

    # =========================================================
    # ACHATS
    # =========================================================
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                DATE(date) AS "Jour",
                COALESCE(SUM(quantite_kg), 0) AS "Achats"
            FROM achats
            GROUP BY DATE(date)
            ORDER BY DATE(date)
        """)

        rows_achats = cur.fetchall()
        colnames_achats = [desc[0] for desc in cur.description]

    df_achats = pd.DataFrame(
        rows_achats,
        columns=colnames_achats
    )

    # =========================================================
    # VENTES
    # =========================================================
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                DATE(date_vente) AS "Jour",
                COALESCE(SUM(quantite_kg), 0) AS "Ventes"
            FROM ventes
            GROUP BY DATE(date_vente)
            ORDER BY DATE(date_vente)
        """)

        rows_ventes = cur.fetchall()
        colnames_ventes = [desc[0] for desc in cur.description]

    df_ventes = pd.DataFrame(
        rows_ventes,
        columns=colnames_ventes
    )

    # =========================================================
    # NORMALISATION DES DATAFRAMES
    # =========================================================

    # Nettoyage des noms de colonnes
    df_achats.columns = df_achats.columns.astype(str).str.strip()
    df_ventes.columns = df_ventes.columns.astype(str).str.strip()

    # Sécurité : garantir la présence de Jour
    if "Jour" not in df_achats.columns:
        st.error(
            f"❌ La colonne 'Jour' est absente de df_achats. "
            f"Colonnes reçues : {list(df_achats.columns)}"
        )
        st.stop()

    if "Jour" not in df_ventes.columns:
        st.error(
            f"❌ La colonne 'Jour' est absente de df_ventes. "
            f"Colonnes reçues : {list(df_ventes.columns)}"
        )
        st.stop()

    # Conversion des dates
    df_achats["Jour"] = pd.to_datetime(
        df_achats["Jour"],
        errors="coerce"
    )

    df_ventes["Jour"] = pd.to_datetime(
        df_ventes["Jour"],
        errors="coerce"
    )

    # Conversion des quantités
    df_achats["Achats"] = pd.to_numeric(
        df_achats["Achats"],
        errors="coerce"
    ).fillna(0)

    df_ventes["Ventes"] = pd.to_numeric(
        df_ventes["Ventes"],
        errors="coerce"
    ).fillna(0)

    # Suppression des dates invalides
    df_achats = df_achats.dropna(subset=["Jour"])
    df_ventes = df_ventes.dropna(subset=["Jour"])

    # =========================================================
    # FUSION
    # =========================================================

    df_merged = pd.merge(
        df_achats[["Jour", "Achats"]],
        df_ventes[["Jour", "Ventes"]],
        on="Jour",
        how="outer"
    )

    df_merged["Achats"] = df_merged["Achats"].fillna(0)
    df_merged["Ventes"] = df_merged["Ventes"].fillna(0)

    df_merged = df_merged.sort_values(
        "Jour"
    ).reset_index(drop=True)

    # =========================================================
    # AFFICHAGE DU GRAPHIQUE
    # =========================================================

    if not df_merged.empty:

        # -----------------------------------------------------
        # IMPORTANT :
        # Conversion pandas -> listes Python simples
        # Évite le problème Plotly / Narwhals / Python 3.14
        # -----------------------------------------------------

        jours = (
            df_merged["Jour"]
            .dt.strftime("%Y-%m-%d")
            .tolist()
        )

        achats = (
            pd.to_numeric(
                df_merged["Achats"],
                errors="coerce"
            )
            .fillna(0)
            .astype(float)
            .tolist()
        )

        ventes = (
            pd.to_numeric(
                df_merged["Ventes"],
                errors="coerce"
            )
            .fillna(0)
            .astype(float)
            .tolist()
        )

        # -----------------------------------------------------
        # CRÉATION DU GRAPHIQUE
        # -----------------------------------------------------

        fig = go.Figure()

        # =========================
        # ACHATS
        # =========================

        fig.add_trace(
            go.Scatter(
                x=jours,
                y=achats,
                name="Achats (Entrées)",
                mode="lines+markers",
                line=dict(
                    width=3,
                    color="#D97706"
                ),
                fill="tozeroy",
                fillcolor="rgba(217, 119, 6, 0.10)"
            )
        )

        # =========================
        # VENTES
        # =========================

        fig.add_trace(
            go.Scatter(
                x=jours,
                y=ventes,
                name="Ventes (Sorties)",
                mode="lines+markers",
                line=dict(
                    width=3,
                    color="#059669"
                ),
                fill="tozeroy",
                fillcolor="rgba(5, 150, 105, 0.10)"
            )
        )

        # -----------------------------------------------------
        # MISE EN FORME
        # -----------------------------------------------------

        fig.update_layout(
            template="plotly_white",
            margin=dict(
                l=20,
                r=20,
                t=30,
                b=20
            ),
            height=380,
            hovermode="x unified",
            xaxis_title="Date",
            yaxis_title="Quantité (kg)",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )

        # -----------------------------------------------------
        # AFFICHAGE
        # -----------------------------------------------------

        st.plotly_chart(
            fig,
            use_container_width=True,
            key="dashboard_flux_achats_ventes"
        )

    else:

        st.info(
            "💡 Aucune donnée d'achat ou de vente disponible "
            "pour afficher l'évolution temporelle."
        )
    # ---------------------------------------------------------
    # 5. RECHERCHE INTELLIGENTE STYLE MOTEUR (inchangée)
    # ---------------------------------------------------------
    st.markdown("### 🔎 Moteur de Recherche Rapide")

    with st.container(border=True):
        search_term = st.text_input(
            "Recherche globale dans l'application",
            placeholder="Entrez un nom de client, fournisseur, N° de Lot ou Contrat...",
            label_visibility="collapsed"
        )

        if search_term:
            param = f"%{search_term}%"
            st.markdown(f"**Résultats de la recherche pour :** `{search_term}`")

            col_a, col_v = st.columns(2)

            # --- Recherche Achats ---
            with col_a:
                try:
                    query_achats = """
                        SELECT a.date as Date, a.numero_de_lot as Lot, f.nom as Fournisseur,
                               a.quantite_kg as Quantite, a.total as Total
                        FROM achats a
                        JOIN fournisseurs f ON a.id_fournisseur = f.id
                        WHERE f.nom LIKE %s OR a.numero_de_lot LIKE %s OR a.numero_contrat LIKE %s
                        LIMIT 5
                    """
                    df_search_a = get_dataframe_from_query(query_achats, params=(param, param, param))
                    if not df_search_a.empty:
                        st.caption("🛒 **Achats trouvés**")
                        st.dataframe(
                            df_search_a,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Quantite": st.column_config.NumberColumn("Quantité", format="%d kg"),
                                "Total": st.column_config.NumberColumn("Total", format="%d FCFA")
                            }
                        )
                    else:
                        st.caption("🛒 Aucun achat ne correspond.")
                except Exception as e:
                    logging.error(f"Erreur recherche achats: {e}")

            # --- Recherche Ventes ---
            with col_v:
                try:
                    query_ventes = """
                        SELECT v.date_vente as Date, c.nom as Client, v.quantite_kg as Quantite,
                               v.total as Total, v.devise as Devise
                        FROM ventes v
                        JOIN clients c ON v.id_client = c.id
                        WHERE c.nom LIKE %s
                        LIMIT 5
                    """
                    df_search_v = get_dataframe_from_query(query_ventes, params=(param,))
                    if not df_search_v.empty:
                        st.caption("🤝 **Ventes trouvées**")
                        st.dataframe(
                            df_search_v,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Quantite": st.column_config.NumberColumn("Quantité", format="%d kg"),
                                "Total": st.column_config.NumberColumn("Total", format="%d {Devise}")
                            }
                        )
                    else:
                        st.caption("🤝 Aucune vente ne correspond.")
                except Exception as e:
                    logging.error(f"Erreur recherche ventes: {e}")
                    
elif choix == "🧾 Achats (Entrees)":
    st.title("🧾 Gestion des Achats & Suivi Reste à Payer")
    st.markdown("Gérez vos acquisitions, éditez vos documents officiels et suivez vos dettes fournisseurs de manière centralisée.")
    st.divider()
    
    if "dernier_achat_traite" not in st.session_state:
        st.session_state.dernier_achat_traite = ""
        
    tab1, tab2, tab3 = st.tabs(["🛒 Nouvel Achat", "📄 Historique & Documents", "💸 Règlement des Dettes"])
    
    # Récupération des magasins (curseur local)
    magasins_liste = fetch_all("SELECT nom FROM magasins")
    liste_noms_magasins = [m[0] for m in magasins_liste]

    # ==========================================
    # TAB 1 : NOUVEL ACHAT / FACTURATION
    # ==========================================
    with tab1:
        st.markdown("### 🛠️ Mode d'Acquisition")
        analyse_existe = False
        analyse_data = None
        poids_net_paye = 0.0

        with st.container(border=True):
            type_achat = st.radio(
                "Comment souhaitez-vous enregistrer cette entrée ?",
                ["📥 Facturer un BR / Pesée en attente", "📜 Achat lié à un Contrat", "🛒 Achat Direct (Spot)"],
                horizontal=True,
                label_visibility="collapsed"
            )

        # Fournisseurs
        fournisseurs_dispo = fetch_all("SELECT id, nom FROM fournisseurs")
        dict_f = {f[1]: f[0] for f in fournisseurs_dispo} if fournisseurs_dispo else {}

        # Contrats actifs
        contrats_dispo = fetch_all("""
            SELECT c.id, c.numero_contrat, f.nom, f.id, c.prix_unitaire, c.date_signature
            FROM contrats c JOIN fournisseurs f ON c.id_fournisseur = f.id
            WHERE c.statut IN ('Actif', 'VALIDE') ORDER BY c.id DESC
        """)
        dict_c = {f"Contrat {c[1]} — {c[2]} (P.U: {c[4]:,.0f} FCFA)": c for c in contrats_dispo} if contrats_dispo else {}

        # BR en attente
        br_en_attente = fetch_all("""
            SELECT a.id, a.numero_de_lot, f.nom, a.quantite_kg, a.date, a.numero_contrat, 
                   a.poids_brut, a.poids_net, a.nombre_de_sacs, a.id_fournisseur, a.poids_net_paye
            FROM achats a 
            JOIN fournisseurs f ON a.id_fournisseur = f.id
            WHERE a.statut = 'En attente de facturation' 
            ORDER BY a.id DESC
        """)
        dict_br = {f"Contrat: {b[5]} | Lot: {b[1]} | {b[2]} | {b[3]} kg (Reçu le {b[4]})": b for b in br_en_attente} if br_en_attente else {}

        # Numéro de lot auto
        try:
            next_achat_id_row = fetch_one("SELECT COALESCE(MAX(id), 0) + 1 FROM achats")
            next_achat_id = next_achat_id_row[0] if next_achat_id_row else 1
        except:
            next_achat_id = 1
        num_lot_auto = f"LOT-{datetime.now().strftime('%Y%m%d')}-{next_achat_id:04d}"

        id_achat_br, ncc, nom_f, id_f = None, "ACHAT-SPOT", "", None
        pu_contrat_par_defaut, qte_defaut, nds_defaut = 0.0, 0.0, 0
        pb_defaut, pn_defaut, num_lot_valeur = "", "", num_lot_auto
        qte_a_facturer = 0.0
        id_contrat = None

        with st.container(border=True):
            if type_achat == "📥 Facturer un BR / Pesée en attente":
                if not dict_br:
                    st.success("🎉 Aucun lot en attente de facturation.")
                else:
                    br_selectionne = st.selectbox("Sélectionner le BR / Pesée à facturer *", list(dict_br.keys()))
                    infos_br = dict_br[br_selectionne]
                    id_achat_br, num_lot_valeur, nom_f, qte_defaut, date_br, ncc, pb_defaut, pn_defaut, nds_defaut, id_f, poids_net_paye = infos_br

                    analyse_existe = False
                    analyse_data = None
                    if id_achat_br:
                        row_analyse = fetch_one("""
                            SELECT aq.taux_humidite, aq.taux_debris_tamisage, aq.taux_corps_etrangers,
                                   aq.taux_feves_plates, aq.feves_moisies_pct, aq.feves_ardoisees_pct,
                                   aq.feves_mitees_pct, aq.feves_germees_pct, aq.taux_crabots,
                                   aq.taux_feves_brisees, aq.taux_fragments_coques,
                                   a.poids_net_paye, aq.statut_qualite
                            FROM analyses_qualite aq
                            JOIN achats a ON aq.id_achat = a.id
                            WHERE aq.id_achat = %s
                        """, (id_achat_br,))
                        if row_analyse:
                            analyse_existe = True
                            analyse_data = {
                                "humidite": row_analyse[0],
                                "debris": row_analyse[1],
                                "etrangers": row_analyse[2],
                                "plates": row_analyse[3],
                                "moisies": row_analyse[4],
                                "ardoises": row_analyse[5],
                                "mitees": row_analyse[6],
                                "germees": row_analyse[7],
                                "crabots": row_analyse[8],
                                "brisees": row_analyse[9],
                                "frag": row_analyse[10],
                                "poids_net_paye": row_analyse[11],
                                "statut_qualite": row_analyse[12]
                            }
                            poids_net_paye = row_analyse[11] if row_analyse[11] else pn_defaut

                    if not analyse_existe:
                        st.warning("⚠️ Ce lot n'a pas encore été analysé. Facturation impossible sans analyse.")
                        st.info("Veuillez vous rendre dans l'onglet '🧪 Unité d'Analyse'.")
                        st.stop()
                    else:
                        st.success(f"✅ Analyse qualité effectuée le {date_br} — Statut : {analyse_data['statut_qualite']}")
                        with st.expander("📊 Détail des réfractions appliquées"):
                            cols = st.columns(4)
                            cols[0].metric("Humidité", f"{analyse_data['humidite']:.1f} %")
                            cols[1].metric("Débris tamisage", f"{analyse_data['debris']:.1f} %")
                            cols[2].metric("Corps étrangers", f"{analyse_data['etrangers']:.1f} %")
                            cols[3].metric("Fèves plates", f"{analyse_data['plates']:.1f} %")
                            cols[0].metric("Moisissures", f"{analyse_data['moisies']:.1f} %")
                            cols[1].metric("Ardoises", f"{analyse_data['ardoises']:.1f} %")
                            cols[2].metric("Autres défauts", f"{analyse_data['mitees']+analyse_data['germees']+analyse_data['crabots']+analyse_data['brisees']+analyse_data['frag']:.1f} %")
                            st.metric("Poids net payable", f"{poids_net_paye:,.2f} kg")
                        
                    if ncc and ncc != "ACHAT-SPOT":
                        row_c = fetch_one("SELECT prix_unitaire FROM contrats WHERE numero_contrat = %s", (ncc,))
                        if row_c:
                            pu_contrat_par_defaut = row_c[0]
                            st.info(f"🔗 **Contrat {ncc}** : Prix unitaire verrouillé à **{pu_contrat_par_defaut:,.0f} FCFA/kg**.")

            elif type_achat == "📜 Achat lié à un Contrat":
                if not dict_c:
                    st.warning("⚠️ Aucun contrat actif enregistré.")
                else:
                    contrat_selectionne = st.selectbox("Sélectionner le Contrat lié *", list(dict_c.keys()))
                    infos_c = dict_c[contrat_selectionne]
                    id_contrat, ncc, nom_f, id_f, pu_contrat_par_defaut, ddc = infos_c[0], infos_c[1], infos_c[2], infos_c[3], infos_c[4], infos_c[5]
            else:
                if not dict_f:
                    st.warning("⚠️ Aucun fournisseur enregistré.")
                else:
                    f_selectionne = st.selectbox("Sélectionner le Fournisseur *", list(dict_f.keys()))
                    ncc, nom_f, id_f, pu_contrat_par_defaut = "ACHAT-SPOT", f_selectionne, dict_f[f_selectionne], 0.0

        # Formulaire principal
        with st.form("form_achat", clear_on_submit=True):
            st.subheader("💵 Informations Financières")
            c1, c2, c3, c4 = st.columns(4)
            qte = c1.number_input(
                "Qte Nette à facturer (kg) *",
                min_value=0.0,
                value=float(poids_net_paye) if analyse_existe and poids_net_paye > 0 else float(qte_a_facturer),
                step=50.0,
                help="La quantité est fixée par le poids net payable issu de l'analyse."
            )
            if analyse_existe:
                st.info(f"💡 Le montant brut est calculé sur la base du poids net payable ({poids_net_paye:,.2f} kg) × prix unitaire.")
            pu = c2.number_input("Prix Unitaire (FCFA) *", value=float(pu_contrat_par_defaut), step=50.0)
            statut = c3.selectbox("Statut Paiement", ["Paye", "Avance", "Non Paye"])
            avance_saisie = c4.number_input("Montant Versé (Si Avance)", 0.0, step=5000.0)

            st.markdown("---")
            st.subheader("📉 Frais & Déductions")
            f1, f2 = st.columns(2)
            montant_deduction = f1.number_input("Montant à déduire (FCFA)", min_value=0.0, step=1000.0, help="Transport, Décote qualité...")
            motif_deduction = f2.text_input("Motif détaillé", placeholder="Ex: Décote humidité > 8%...")

            st.markdown("---")
            st.subheader("📦 Logistique & Stockage")
            d1, d2, d3, d4, d5 = st.columns(5)
            ndl = d1.text_input("Numéro de Lot", value=num_lot_valeur, disabled=True)
            pb = d2.text_input("Poids Brut (kg)", value=str(pb_defaut))
            pn = d3.text_input("Poids Net (kg)", value=str(pn_defaut))
            nds = d4.number_input("Nombre de Sacs", min_value=0, value=int(nds_defaut), step=1)
            
            index_magasin = 0
            if type_achat == "📥 Facturer un BR / Pesée en attente" and num_lot_valeur:
                mag_associe = fetch_one("""
                    SELECT magasin_destination FROM stock 
                    WHERE (commentaire LIKE %s OR commentaire LIKE %s) AND type = 'Entrée'
                """, (f"%Lot N°{num_lot_valeur}%", f"%Lot {num_lot_valeur}%"))
                if mag_associe and mag_associe[0] in liste_noms_magasins:
                    index_magasin = liste_noms_magasins.index(mag_associe[0])

            if liste_noms_magasins:
                lieu = d5.selectbox("Magasin de Stockage *", liste_noms_magasins, index=index_magasin)
            else:
                d5.error("⚠️ Aucun magasin créé !")
                lieu = None

            st.markdown("<br>", unsafe_allow_html=True)
            submitted = st.form_submit_button("💰 Valider et Facturer ce Lot", type="primary", use_container_width=True) 

            if submitted:
                total_brut = qte * pu
                total_net = total_brut - montant_deduction
                if type_achat == "📥 Facturer un BR / Pesée en attente" and not analyse_existe:
                    st.error("❌ La facturation est impossible : ce lot n'a pas été analysé.")
                    st.stop()
                if id_f is None:
                    st.error("❌ Sélectionnez un fournisseur, un contrat ou un bon de réception valide.")
                elif qte <= 0 or pu <= 0:
                    st.error("❌ La quantité et le prix unitaire doivent être > 0.")
                elif lieu is None:
                    st.error("❌ Enregistrez un magasin de stockage d'abord.")
                elif statut == "Avance" and (avance_saisie <= 0 or avance_saisie >= total_net):
                    st.error("❌ L'avance versée doit être entre 0 et le net à payer.")
                else:
                    empreinte_achat = f"{nom_f}_{qte}_{pu}_{ndl}"
                    if st.session_state.dernier_achat_traite == empreinte_achat:
                        st.warning("⚠️ Double soumission détectée.")
                    else:
                        mt_avance = total_net if statut == "Paye" else (0.0 if statut == "Non Paye" else avance_saisie)
                        date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                        try:
                            with conn.cursor() as cur:
                                if type_achat == "📥 Facturer un BR / Pesée en attente" and id_achat_br:
                                    cur.execute("""
                                        UPDATE achats
                                        SET date = %s, quantite_kg = %s, prix_unitaire = %s, total = %s, statut = %s, 
                                            montant_avance = %s, poids_brut = %s, poids_net = %s, nombre_de_sacs = %s, 
                                            deductions = %s, libelle_deductions = %s, poids_net_paye = %s
                                        WHERE id = %s
                                    """, (date_now, qte, pu, total_net, statut, mt_avance, pb, pn, nds, montant_deduction, motif_deduction, qte, id_achat_br))

                                    cur.execute("""
                                        UPDATE stock
                                        SET quantite_kg = %s, commentaire = %s
                                        WHERE (commentaire LIKE %s OR commentaire LIKE %s) AND type = 'Entrée'
                                    """, (qte, f"Lot {ndl} - Contrat: {ncc} - Fourn: {nom_f} (Facturé)", f"%Lot N°{ndl}%", f"%Lot {ndl}%"))
                                    log_msg = f"Facturation finalisée - Lot {ndl} (Contrat {ncc})"
                                else:
                                    cur.execute("""
                                        INSERT INTO achats (date, id_fournisseur, quantite_kg, prix_unitaire, total, statut, montant_avance, numero_de_lot, numero_contrat, poids_brut, poids_net, nombre_de_sacs, deductions, libelle_deductions)
                                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                                        RETURNING id
                                    """, (date_now, id_f, qte, pu, total_net, statut, mt_avance, ndl, ncc, pb, pn, nds, montant_deduction, motif_deduction))
                                    id_achat = cur.fetchone()[0]

                                    cur.execute("""
                                        INSERT INTO stock (date, type, quantite_kg, origine, magasin_destination, commentaire) 
                                        VALUES (%s,%s,%s,%s,%s,%s)
                                    """, (date_now, "Entrée", qte, "Achat", lieu, f"Lot {ndl} - Contrat: {ncc} - Fourn: {nom_f} (Facturé direct)"))
                                    log_msg = f"Achat direct ({ncc}) lot {ndl} chez {nom_f} (Stock : {lieu})"

                                conn.commit()
                            if 'get_stock_actuel' in globals():
                                get_stock_actuel.clear()

                            log_action(log_msg)
                            st.session_state.dernier_achat_traite = empreinte_achat
                            st.success(f"✅ Lot {ndl} facturé ! Reste à payer : {total_net - mt_avance:,.0f} FCFA")
                            st.rerun()

                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur critique lors de la transaction : {e}")

    # ==========================================
    # TAB 2 : HISTORIQUE GÉNÉRAL
    # ==========================================
    with tab2:
        # Utilisation de get_dataframe_from_query pour éviter SQLAlchemy
        df = get_dataframe_from_query("""
            SELECT 
                a.id, a.date, f.nom as Fournisseur, a.numero_de_lot as "N° Lot", 
                a.quantite_kg as "Qte (kg)", a.prix_unitaire as PU, 
                a.total as "Total Net (FCFA)", a.montant_avance as "Avance Versée (FCFA)", 
                (a.total - a.montant_avance) as "Reste à Payer", a.statut as Statut, 
                a.numero_contrat as "N° Contrat", a.poids_brut as "Poids Brut", 
                a.poids_net as "Poids Net", f.numero_de_compte as "N° Compte Fournisseur",
                f.id as id_fourn, a.deductions as Deductions, a.libelle_deductions as "Motif Déduction"
            FROM achats a JOIN fournisseurs f ON a.id_fournisseur = f.id
            WHERE a.statut != 'En attente de facturation' ORDER BY a.id DESC
        """)

        if not df.empty:
            st.markdown("### 📊 Vue d'Ensemble")
            kpi1, kpi2, kpi3 = st.columns(3)
            kpi1.metric("Volume Total (kg)", f"{df['Qte (kg)'].sum():,.0f}")
            kpi2.metric("Achats Validés (FCFA)", f"{df['Total Net (FCFA)'].sum():,.0f}")
            kpi3.metric("Dettes Fournisseurs (FCFA)", f"{df['Reste à Payer'].sum():,.0f}", delta_color="inverse")

            st.markdown("<br>", unsafe_allow_html=True)
            filtre_f = st.text_input("🔎 Recherche rapide par fournisseur...", placeholder="Tapez un nom...")
            if filtre_f:
                df = df[df["Fournisseur"].str.contains(filtre_f, case=False, na=False)]

            st.dataframe(
                df, use_container_width=True, hide_index=True,
                column_config={
                    "PU": st.column_config.NumberColumn(format="%d FCFA"),
                    "Total Net (FCFA)": st.column_config.NumberColumn(format="%d FCFA"),
                    "Avance Versée (FCFA)": st.column_config.NumberColumn(format="%d FCFA"),
                    "Reste à Payer": st.column_config.NumberColumn(format="%d FCFA"),
                    "Deductions": st.column_config.NumberColumn(format="%d FCFA")
                }
            )

            st.divider()
            st.markdown("### 🖨️ Pôle Documentaire")

            col_gen, col_dl = st.columns(2)

            with col_gen:
                with st.container(border=True):
                    st.subheader("1. Éditer un nouveau document")
                    # Convertir les lignes en listes pour le selectbox
                    rows = df.values.tolist()
                    sel = st.selectbox(
                        "Sélectionner un achat :", rows,
                        format_func=lambda x: f"Lot: {x[3]} | {x[2]} (Net: {x[6]:,.0f} F)"
                    )

                    if sel:
                        id_f_selectionne, compte_principal = sel[14], sel[13]
                        comptes_annexes = fetch_all(
                            "SELECT type_compte, nom_institution, numero_compte, titulaire FROM comptes_fournisseurs WHERE id_fournisseur = %s",
                            (id_f_selectionne,)
                        )

                        options_paiement = [f"[Bancaire] {compte_principal}"] if compte_principal and compte_principal != "N/A" else []
                        options_paiement.extend([f"[{c[0]}] {c[1]} - {c[2]} ({c[3]})" for c in comptes_annexes])
                        options_paiement.extend(["[Espèces] Paiement Cash", "[Chèque] Paiement par Chèque", "[Mobile Money] Paiement par Mobile Money"])

                        compte_choisi = st.selectbox("💳 Mode de règlement :", options_paiement)
                        mode_regl_propre = compte_choisi.split("]")[0].replace("[", "").strip()
                        compte_propre = "N/A" if mode_regl_propre in ["Espèces", "Mobile Money", "Chèque"] else compte_choisi.split("] ", 1)[1].strip()

                        data_p = {
                            "num_paiement": f"PAY-{sel[0]}-{sel[3]}",
                            "date": sel[1],
                            "fournisseur": sel[2],
                            "num_contrat": sel[10] or "N/A",
                            "num_lot": sel[3] or "N/A",
                            "mode_reglement": mode_regl_propre,
                            "num_compte": compte_propre,
                            "total": float(sel[6]),
                            "versement": float(sel[7]),
                            "reste": float(sel[8]),
                            "deductions": float(sel[15]) if sel[15] else 0.0,
                            "libelle_deductions": sel[16] or ""
                        }

                        if st.button("📄 Bordereau de Paiement", use_container_width=True):
                            with conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO documents_generes (type_doc, reference, montant, demandeur, description, statut)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                """, ('bon_paiement', data_p.get('num_paiement'), data_p.get('total'),
                                      st.session_state.get('username', 'Agent'), 'Bordereau de détail', 'EN_ATTENTE'))
                                conn.commit()
                            st.toast("📥 Bordereau soumis avec succès !")

                        if st.button("💵 Bon de Caisse (Acompte)", use_container_width=True):
                            with conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO documents_generes (type_doc, reference, montant, demandeur, description, statut)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                """, ('bon_caisse', data_p.get('num_paiement'), data_p.get('versement'),
                                      st.session_state.get('username', 'Agent'), 'Bon de caisse / Acompte', 'EN_ATTENTE'))
                                conn.commit()
                            st.toast("📥 Bon de Caisse soumis !")

                        if float(sel[8]) > 0:
                            if st.button("📝 Reconnaissance Dette", use_container_width=True):
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        INSERT INTO documents_generes (type_doc, reference, montant, demandeur, description, statut)
                                        VALUES (%s, %s, %s, %s, %s, %s)
                                    """, ('engagement_dette', data_p.get('num_paiement'), float(sel[8]),
                                          st.session_state.get('username', 'Agent'), 'Reconnaissance de dette', 'EN_ATTENTE'))
                                    conn.commit()
                                st.toast("📥 Engagement de dette soumis !")
                        else:
                            st.success("✅ Achat soldé, aucune dette.")

            with col_dl:
                with st.container(border=True):
                    st.subheader("2. Télécharger les validés")
                    df_valides = get_dataframe_from_query(
                        "SELECT id, type_doc, reference, montant, demandeur, description, statut FROM documents_generes WHERE statut = 'VALIDE' ORDER BY id DESC"
                    )

                    if df_valides.empty:
                        st.info("ℹ️ Aucun document validé disponible.")
                    else:
                        doc_sel = st.selectbox(
                            "Sélectionner un document PDF :", df_valides.values.tolist(),
                            format_func=lambda x: f"[{x[1].upper()}] Réf: {x[2]}"
                        )

                        if doc_sel and st.button("🖨️ Générer le PDF", type="primary", use_container_width=True):
                            id_doc, type_doc, ref_doc = doc_sel[0], doc_sel[1], doc_sel[2]
                            try:
                                row_sign = fetch_one("SELECT signataire FROM documents_generes WHERE id = %s", (id_doc,))
                                signataire_doc = row_sign[0] if row_sign else None

                                cachet_a_utiliser = None
                                if signataire_doc:
                                    res_cachet = fetch_one("SELECT fichier_cachet FROM cachets_direction WHERE role_signataire = %s", (signataire_doc,))
                                    cachet_a_utiliser = res_cachet[0] if res_cachet else None

                                if not cachet_a_utiliser:
                                    res_cachet = fetch_one("SELECT fichier_cachet FROM cachets_direction WHERE role_signataire = 'DG'")
                                    cachet_a_utiliser = res_cachet[0] if res_cachet else None

                                id_achat = None
                                if ref_doc:
                                    if ref_doc.startswith("PAY-") and len(ref_doc.split('-')) > 1:
                                        id_achat = int(ref_doc.split('-')[1])
                                    elif ref_doc.startswith("REG-"):
                                        match = re.search(r"REG-(\d+)-", ref_doc)
                                        if match:
                                            id_achat = int(match.group(1))
                                if not id_achat:
                                    st.error("❌ Impossible d'extraire l'ID de l'achat.")
                                    st.stop()

                                row = fetch_one("""
                                    SELECT a.id, a.numero_de_lot, f.nom, a.quantite_kg, a.prix_unitaire, 
                                           a.total, a.montant_avance, a.numero_contrat, a.poids_net, a.deductions, a.libelle_deductions
                                    FROM achats a JOIN fournisseurs f ON a.id_fournisseur = f.id WHERE a.id = %s
                                """, (id_achat,))

                                if not row:
                                    st.error("❌ Achat introuvable.")
                                    st.stop()

                                # Récupérer code + montant
                                row_code = fetch_one("SELECT code_verification, montant FROM documents_generes WHERE id = %s", (id_doc,))
                                code_verif = row_code[0] if row_code else None
                                montant_doc = float(row_code[1] or 0.0) if row_code else 0.0

                                total_achat = float(row[5] or 0.0)
                                avance_actuelle = float(row[6] or 0.0)

                                data_paiement = {
                                    'num_paiement': ref_doc,
                                    'date': datetime.now().strftime('%d/%m/%Y'),
                                    'fournisseur': row[2],
                                    'num_lot': row[1],
                                    'num_contrat': row[7] or 'N/A',
                                    'quantite_kg': float(row[3] or 0.0),
                                    'prix_unitaire': float(row[4] or 0.0),
                                    'total': total_achat,
                                    'poids_net': float(row[8] or 0.0),
                                    'deductions': float(row[9] or 0.0),
                                    'libelle_deductions': row[10] or '',
                                    'mode_reglement': 'Virement bancaire',
                                    'code_verification': code_verif,
                                    'montant_regle': montant_doc,
                                }

                                if type_doc == 'reglement_dette':
                                    avance_avant = max(0.0, avance_actuelle - montant_doc)
                                    dette_initiale = max(0.0, total_achat - avance_avant)
                                    data_paiement['dette_initiale'] = dette_initiale
                                    data_paiement['montant_regle'] = montant_doc
                                    data_paiement['versement'] = montant_doc
                                    data_paiement['reste'] = max(0.0, dette_initiale - montant_doc)
                                elif type_doc in ['bon_paiement', 'bon_caisse', 'engagement_dette']:
                                    data_paiement['versement'] = montant_doc if montant_doc > 0 else avance_actuelle
                                    data_paiement['reste'] = max(0.0, total_achat - avance_actuelle)
                                else:
                                    data_paiement['versement'] = avance_actuelle
                                    data_paiement['reste'] = max(0.0, total_achat - avance_actuelle)

                                if type_doc in ['bon_paiement', 'bon_caisse', 'engagement_dette', 'reglement_dette']:
                                    res_pdf = generer_bon_paiement_pdf(
                                        data_paiement=data_paiement,
                                        type_document=type_doc,
                                        signataire=signataire_doc if signataire_doc else "DG",
                                        cachet_blob=cachet_a_utiliser
                                    )
                                else:
                                    st.error("❌ Type non supporté.")
                                    st.stop()

                                path_pdf, pdf_bytes = None, None
                                if isinstance(res_pdf, tuple):
                                    for item in res_pdf:
                                        if isinstance(item, str):
                                            path_pdf = item
                                        elif isinstance(item, bytes):
                                            pdf_bytes = item
                                elif isinstance(res_pdf, str):
                                    path_pdf = res_pdf
                                elif isinstance(res_pdf, bytes):
                                    pdf_bytes = res_pdf

                                if path_pdf and os.path.exists(path_pdf):
                                    with open(path_pdf, "rb") as f:
                                        pdf_bytes = f.read()
                                    try:
                                        os.remove(path_pdf)
                                    except:
                                        pass

                                if pdf_bytes:
                                    st.download_button(
                                        label=f"💾 Cliquez ici pour enregistrer",
                                        data=pdf_bytes,
                                        file_name=f"{type_doc}_{ref_doc}.pdf",
                                        mime="application/pdf",
                                        use_container_width=True
                                    )
                                else:
                                    st.error("❌ Impossible de générer le fichier PDF.")

                            except Exception as e:
                                st.error(f"❌ Erreur de génération : {e}")

    # ==========================================
    # TAB 3 : RÈGLEMENT DES DETTES
    # ==========================================
    with tab3:
        st.markdown("### 💸 Guichet de Règlement des Dettes")

        achats_dettes = fetch_all("""
            SELECT a.id, f.nom as Fournisseur, a.numero_de_lot, a.total, a.montant_avance, 
                   (a.total - a.montant_avance) as reste_a_payer, a.numero_contrat
            FROM achats a JOIN fournisseurs f ON a.id_fournisseur = f.id
            WHERE (a.total - a.montant_avance) > 0.01 AND a.statut != 'En attente de facturation'
            ORDER BY a.id DESC
        """)

        if not achats_dettes:
            st.success("🎉 Excellente nouvelle ! Aucun reste à payer en attente.")
        else:
            dict_dettes = {f"Lot: {d[2]} | Fournisseur: {d[1]} | Reste: {d[5]:,.0f} FCFA": d for d in achats_dettes}

            with st.form("form_reglement_dette", clear_on_submit=True):
                dette_selectionnee = st.selectbox("Sélectionner la dette à solder *", list(dict_dettes.keys()))
                infos_dette = dict_dettes[dette_selectionnee]
                id_achat, fourn_nom, lot_concerne = infos_dette[0], infos_dette[1], infos_dette[2]
                total_net_dette, avance_actuelle, reste_a_payer_actuel = infos_dette[3], infos_dette[4], infos_dette[5]

                st.markdown("---")
                m1, m2, m3 = st.columns(3)
                m1.metric("Total Facturé", f"{total_net_dette:,.0f} F")
                m2.metric("Déjà Payé", f"{avance_actuelle:,.0f} F")
                m3.metric("Reste à Payer", f"{reste_a_payer_actuel:,.0f} F", delta="- Dette", delta_color="inverse")
                st.markdown("---")

                c_pay1, c_pay2 = st.columns(2)
                montant_regle = c_pay1.number_input(
                    "Nouveau montant à verser (FCFA) *",
                    min_value=0.0,
                    max_value=float(reste_a_payer_actuel),
                    step=5000.0
                )
                date_reglement = c_pay2.date_input("Date d'opération", value=date.today())

                id_f_dette = fetch_one("SELECT id_fournisseur FROM achats WHERE id = %s", (id_achat,))[0]
                compte_f_principal = fetch_one("SELECT numero_de_compte FROM fournisseurs WHERE id = %s", (id_f_dette,))[0]
                comptes_f_annexes = fetch_all(
                    "SELECT type_compte, nom_institution, numero_compte, titulaire FROM comptes_fournisseurs WHERE id_fournisseur = %s",
                    (id_f_dette,)
                )

                options_regl = [f"[Principal] {compte_f_principal}"] if compte_f_principal and compte_f_principal != "N/A" else []
                options_regl.extend([f"[{ca[0]}] {ca[1]} - {ca[2]} ({ca[3]})" for ca in comptes_f_annexes])
                options_regl.extend(["[Espèces] Paiement Cash"])

                mode_regl_dette = st.selectbox("Mode de Paiement :", options_regl)

                st.markdown("<br>", unsafe_allow_html=True)
                submit_reglement = st.form_submit_button("✅ Valider le paiement", type="primary", use_container_width=True)

                if submit_reglement:
                    if montant_regle <= 0:
                        st.error("❌ Le montant du règlement doit être supérieur à 0.")
                    elif montant_regle > reste_a_payer_actuel:
                        st.error(f"❌ Le montant saisi ({montant_regle:,.0f} FCFA) dépasse le reste à payer ({reste_a_payer_actuel:,.0f} FCFA).")
                    else:
                        nouvelle_avance = avance_actuelle + montant_regle
                        nouveau_reste = total_net_dette - nouvelle_avance
                        nouveau_statut = "Paye" if nouveau_reste <= 0.1 else "Avance"

                        with conn.cursor() as cur:
                            cur.execute("UPDATE achats SET montant_avance = %s, statut = %s WHERE id = %s",
                                        (nouvelle_avance, nouveau_statut, id_achat))

                            ref_reglement = f"REG-{id_achat}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
                            cur.execute("""
                                INSERT INTO documents_generes (type_doc, reference, montant, demandeur, description, statut)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """, (
                                'reglement_dette',
                                ref_reglement,
                                montant_regle,
                                st.session_state.get('username', 'Agent'),
                                f"Règlement partiel/solde du lot {lot_concerne} (Fournisseur: {fourn_nom}) - Montant: {montant_regle:,.0f} FCFA",
                                'EN_ATTENTE'
                            ))
                            conn.commit()

                        log_action(f"Dette réglée de {montant_regle:,.0f} FCFA pour l'achat N°{id_achat} (Lot {lot_concerne}) - Document {ref_reglement} créé")
                        st.success(f"✅ Paiement de {montant_regle:,.0f} FCFA enregistré ! Reste dû : {nouveau_reste:,.0f} FCFA. Le document de règlement (réf. {ref_reglement}) a été soumis à la Direction pour validation.")
                        st.rerun()                  
elif choix == "🛍️ Ventes (Sorties)":
    st.title("🛍️ Gestion des Ventes & Exportations")
    
    stock_actuel = get_stock_actuel()
    st.metric("📦 Stock Actuel Global", f"{stock_actuel:,.2f} kg")
    
    tab1, tab2 = st.tabs(["🤝 Enregistrer un Contrat de Vente", "📄 Historique & Factures Commerciales"])
    
    # ==========================================
    # TAB 1 : ENREGISTREMENT DE LA VENTE
    # ==========================================
    with tab1:
        clients = fetch_all("SELECT id, nom, devise_preferee FROM clients")
        dict_c = {c[1]: {"id": c[0], "devise": c[2]} for c in clients}
        
        magasins_dispo = fetch_all("SELECT id, nom FROM magasins")
        dict_m = {m[1]: m[0] for m in magasins_dispo}
        
        if not clients or not magasins_dispo:
            st.warning("⚠️ Veuillez configurer au moins un client et un magasin avant de procéder.")
        else:
            with st.form("form_vente", clear_on_submit=True):
                st.subheader("👤 Identités & Logistique")
                col1, col2 = st.columns(2)
                nom_c = col1.selectbox("Sélectionner le Client *", list(dict_c.keys()))
                magasin_source = col2.selectbox("Magasin de départ *", list(dict_m.keys()))
                
                st.subheader("🌍 Détails de l'Exportation (International)")
                e1, e2, e3 = st.columns(3)
                incoterm = e1.selectbox("Incoterm *", ["FOB", "CIF", "CFR", "EXW", "DAP"], help="Règle internationale de transfert des risques")
                port_depart = e2.text_input("Port d'embarquement", value="Port de Kribi, Cameroun")
                port_arrivee = e3.text_input("Port de destination")

                st.subheader("💰 Détails Financiers")
                c1, c2, c3 = st.columns(3)
                qte = c1.number_input("Quantité Nette (kg) *", min_value=0.0, step=100.0)
                pu = c2.number_input("Prix Unitaire (PU) *", min_value=0.0, step=10.0)
                devise_client = dict_c[nom_c]["devise"] if nom_c else "XAF"
                
                devises_possibles = ["XAF", "EUR", "USD", "GBP"]
                idx_devise = devises_possibles.index(devise_client) if devise_client in devises_possibles else 0
                devise_app = c3.selectbox("Devise", devises_possibles, index=idx_devise)
                
                c4, c5 = st.columns(2)
                liste_termes = [
                    "90% LIVRAISON ENTREPÔT - 10% APRÈS DÉLIVRANCE DU BILL OF LADING",
                    "90% LIVRAISON ENTREPÔT - 8% APRÈS DÉLIVRANCE BL - 2% À DESTINATION",
                    "90% LIVRAISON ENTREPÔT - 5% APRÈS DÉLIVRANCE BL - 5% À DESTINATION",
                    "100% APRÈS DÉLIVRANCE DU BILL OF LADING"
                ]
                termes_paiement = c4.selectbox("Termes de paiement *", liste_termes)
                statut = c5.selectbox("Statut Paiement", ["En attente", "Avance reçue", "Payé en totalité"])

                st.info("💡 La Commercial Invoice sera générée sur la base de cet Incoterm, de cette devise et de ces termes de paiement.")
                submitted = st.form_submit_button("✅ Valider l'Exportation", use_container_width=True)
                
                if submitted:
                    if qte <= 0 or pu <= 0:
                        st.error("❌ La quantité et le prix unitaire doivent être supérieurs à 0.")
                    else:
                        try:
                            id_c = dict_c[nom_c]["id"]
                            id_m = dict_m[magasin_source]
                            total_vente = qte * pu
                            date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    
                            with conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO ventes 
                                    (date_vente, client_nom, id_magasin, id_client, quantite_kg, prix_unitaire,
                                    montant_total, total, statut_paiement, termes_paiement, statut_livraison,
                                    incoterm, port_embarquement, port_dechargement, devise) 
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'En attente d''expédition', %s, %s, %s, %s)
                                    RETURNING id
                                """, (date_now, nom_c, id_m, id_c, qte, pu, total_vente, total_vente,
                                      statut, termes_paiement, incoterm, port_depart, port_arrivee, devise_app))
                    
                                id_vente = cur.fetchone()[0]
                    
                                cur.execute("""
                                    INSERT INTO documents_generes (type_doc, reference, montant, demandeur, description, statut)
                                    VALUES (%s, %s, %s, %s, %s, %s)
                                """, ('facture_vente', f"INV-{id_vente:04d}", total_vente,
                                      st.session_state.get('username', 'Agent'),
                                      f"Vente à {nom_c} de {qte} kg - Incoterm {incoterm}", 'EN_ATTENTE'))
                    
                                conn.commit()
                            st.success(f"✅ Vente de {qte:,.2f} kg enregistrée sous la référence INV-{id_vente:04d} et soumise à la Direction !")
                            st.rerun()
                        except Exception as e:
                            conn.rollback()
                            st.error(f"❌ Erreur lors de l'enregistrement : {e}")

    # ==========================================
    # TAB 2 : HISTORIQUE ET GÉNÉRATION PDF
    # ==========================================
    with tab2:
        st.divider()
        st.subheader("🖨️ Édition de la Commercial Invoice (Facture Pro)")

        # Requête adaptée pour PostgreSQL (LPAD déjà utilisé)
        df_ventes = get_dataframe_from_query("""
            SELECT v.id, v.id_client, v.date_vente as Date, c.nom as Client, v.quantite_kg as Qte,
                v.prix_unitaire as PU, v.total as Total, v.devise as Devise,
                v.incoterm as Incoterm, v.termes_paiement as Termes,
                v.port_embarquement, v.port_dechargement,
                COALESCE((
                    SELECT statut FROM documents_generes
                    WHERE type_doc = 'facture_vente'
                        AND reference = 'INV-' || LPAD(v.id::text, 4, '0')
                    ORDER BY id DESC LIMIT 1
                ), 'EN_ATTENTE') AS Statut_Validation,
                COALESCE((
                    SELECT signataire FROM documents_generes
                    WHERE type_doc = 'facture_vente'
                        AND reference = 'INV-' || LPAD(v.id::text, 4, '0')
                    ORDER BY id DESC LIMIT 1
                ), '') AS Signataire
            FROM ventes v
            JOIN clients c ON v.id_client = c.id
            ORDER BY v.id DESC
        """)
        
        st.dataframe(df_ventes, use_container_width=True)

        # --- 1. GESTION DES BANQUES ---
        with st.expander("🏦 Ajouter un nouveau compte bancaire"):
            with st.form("form_add_banque", clear_on_submit=True):
                st.info("💡 Ce compte sera disponible pour toutes vos futures factures.")
                b1, b2, b3, b4 = st.columns(4)
                b_nom = b1.text_input("Nom de la Banque *", placeholder="Ex: UBA Cameroun")
                b_swift = b2.text_input("Code SWIFT / BIC *")
                b_iban = b3.text_input("IBAN *")
                b_numero_compte = b4.text_input("Numéro de Compte *")

                if st.form_submit_button("✅ Enregistrer la Banque", use_container_width=True):
                    if b_nom and b_swift and b_iban and b_numero_compte:
                        with conn.cursor() as cur:
                            cur.execute(
                                "INSERT INTO banques (nom, swift, iban, numero_compte) VALUES (%s, %s, %s, %s)", 
                                (b_nom, b_swift, b_iban, b_numero_compte)
                            )
                            conn.commit()
                        st.success(f"La banque {b_nom} a été ajoutée avec succès !")
                        st.rerun()
                    else:
                        st.error("❌ Tous les champs (Nom, SWIFT, IBAN, Numéro de Compte) sont obligatoires.")

        # Après le formulaire et son traitement
            st.divider()
            st.markdown("##### 📋 Banques déjà enregistrées")
            try:
                banques_df = get_dataframe_from_query("SELECT id, nom, swift, iban, numero_compte FROM banques ORDER BY nom")
                if not banques_df.empty:
                    st.dataframe(banques_df, use_container_width=True, hide_index=True)
                    # Option : bouton pour supprimer une banque
                    with st.expander("🗑️ Supprimer une banque"):
                        banques_list = banques_df.values.tolist()
                        dict_banques = {f"{b[1]} ({b[2]})": b[0] for b in banques_list}
                        banque_a_supprimer = st.selectbox("Sélectionner la banque à supprimer", list(dict_banques.keys()))
                        if st.button("❌ Supprimer cette banque", type="primary"):
                            try:
                                with conn.cursor() as cur:
                                    cur.execute("DELETE FROM banques WHERE id = %s", (dict_banques[banque_a_supprimer],))
                                    conn.commit()
                                st.success("Banque supprimée !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur : {e}")
                else:
                    st.info("Aucune banque enregistrée.")
            except Exception as e:
                st.error(f"Erreur lors du chargement des banques : {e}")
    
        # --- 2. SÉLECTION DE LA VENTE ET DE LA BANQUE ---
        if not df_ventes.empty:
            st.divider()
            sel = st.selectbox(
                "📦 Sélectionner une expédition pour générer le document :", 
                df_ventes.values.tolist(), 
                format_func=lambda x: f"INV-{int(x[0]):04d} | Client: {x[3]} | {x[4]:,.2f} kg | {x[6]:,.2f} {x[7]} ({x[10] or 'EN ATTENTE'})"
            )

            banques_db = fetch_all("SELECT nom, swift, iban, numero_compte FROM banques")
            
            if not banques_db:
                st.warning("⚠️ Aucune banque enregistrée. Veuillez en ajouter une via le menu ci-dessus.")
            else:
                dict_banques = {b[0]: {"swift": b[1], "iban": b[2], "numero_compte": b[3]} for b in banques_db}
                choix_banque = st.selectbox("💳 Compte bancaire à afficher sur la facture :", list(dict_banques.keys()))

                # --- 3. GÉNÉRATION DU PDF (Strictement sous condition de validation) ---
                if st.button("📄 Générer la Commercial Invoice en PDF", use_container_width=True, type="primary"):
                    statut_valid = sel[12] if len(sel) > 12 else None
                    signataire = sel[13] if len(sel) > 13 else None

                    if statut_valid != 'VALIDE':
                        st.error("❌ **Impression bloquée !** Cette vente n'a pas encore été validée par la Direction. "
                                 "La Commercial Invoice officielle ne peut pas être générée tant que le document n'est pas approuvé.")
                    else:
                        try:
                            cachet = None
                            if signataire:
                                res_c = fetch_one("SELECT fichier_cachet FROM cachets_direction WHERE role_signataire = %s", (signataire,))
                                if res_c:
                                    cachet = res_c[0]

                            infos_client = fetch_one("SELECT nom, email, pays, nui FROM clients WHERE id = %s", (sel[1],))
                            dict_client = {
                                "nom": infos_client[0] if infos_client else sel[3],
                                "email": infos_client[1] if infos_client else "",
                                "pays": infos_client[2] if infos_client else "",
                                "nui": infos_client[3] if infos_client else ""
                            }

                            ref_doc = f"INV-{int(sel[0]):04d}"
                            row_code = fetch_one("SELECT code_verification FROM documents_generes WHERE reference = %s AND type_doc = %s", (ref_doc, 'facture_vente'))
                            code_verif = row_code[0] if row_code else None
                            poids_net = qte
                            # estimation du nombre de colis (sacs de 60 kg)
                            nb_colis = int(qte / 60) if qte > 0 else 0
                            # poids brut = poids net + (nb_colis * 0.5) (poids d'un sac vide)
                            poids_brut = poids_net + (nb_colis * 0.5)
                            nom_fichier = generer_pdf_international(
                                id_doc=int(sel[0]),
                                date_str=str(sel[2]).split(" ")[0],
                                client=dict_client,
                                poids_brut=poids_brut,
                                poids_net=qte,
                                nb_colis=nb_colis,
                                qte=sel[4],
                                pu=sel[5],
                                total=sel[6],
                                devise=sel[7],
                                incoterm=sel[8],
                                condition_paiement=sel[9],
                                port_depart=sel[10],
                                port_arrivee=sel[11],
                                banque_nom=choix_banque,
                                banque_swift=dict_banques[choix_banque]["swift"],
                                banque_iban=dict_banques[choix_banque]["iban"],
                                banque_numero_compte=dict_banques[choix_banque]["numero_compte"],
                                cachet_blob=cachet
                            )

                            with open(nom_fichier, "rb") as pdf_file:
                                pdf_bytes = pdf_file.read()
                            
                            if os.path.exists(nom_fichier):
                                os.remove(nom_fichier)

                            if code_verif and 'apposer_qr_sur_pdf' in globals():
                                pdf_bytes = apposer_qr_sur_pdf(pdf_bytes, code_verif, ref_doc)

                            st.success("✅ Commercial Invoice officielle générée avec succès !")
                            st.download_button(
                                label="⬇️ Télécharger la Commercial Invoice (PDF)",
                                data=pdf_bytes,
                                file_name=f"Commercial_Invoice_{int(sel[0]):04d}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                        except Exception as ex_gen:
                            st.error(f"❌ Erreur lors de la génération du PDF : {ex_gen}")              

if choix == "🤝 Fournisseurs":
    st.title("🤝 Répertoire des Fournisseurs")
    
    # ---- ONGLETS : liste en premier ----
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📋 Liste",
        "➕ Ajouter",
        "📝 Modifier",
        "💳 Comptes de Paiement",
        "🗑️ Supprimer",
        "📦 Livraisons & Contrats"
    ])

    # ============================================================
    # TAB 1 : LISTE DES FOURNISSEURS
    # ============================================================
    with tab1:
        st.subheader("📋 Tous les fournisseurs")
        
        df_all = get_dataframe_from_query("""
            SELECT 
                id,
                nom,
                telephone,
                ville,
                Rccm,
                nui,
                adresse,
                pays,
                code_postal,
                adresse_complete,
                tva_intra,
                devise_preferee,
                condition_paiement,
                langue_facture,
                numero_de_compte,
                email,
                COALESCE(TO_CHAR(date_ajout, 'DD/MM/YYYY'), '—') AS date_ajout
            FROM fournisseurs
            ORDER BY id DESC
        """)

        if df_all.empty:
            st.info("Aucun fournisseur enregistré pour le moment.")
        else:
            total = len(df_all)
            derniers = df_all.head(3)['nom'].tolist()
            col_met1, col_met2, col_met3 = st.columns(3)
            col_met1.metric("🏢 Total fournisseurs", total)
            col_met2.metric("📅 Derniers ajouts", ", ".join(derniers) if derniers else "Aucun")
            col_met3.metric("📞 Avec téléphone", df_all['telephone'].notna().sum())

            st.divider()

            search = st.text_input("🔍 Rechercher un fournisseur (nom, téléphone, ville)", placeholder="Ex: ETS, 677...")
            if search:
                mask = (
                    df_all['nom'].str.contains(search, case=False, na=False) |
                    df_all['telephone'].str.contains(search, case=False, na=False) |
                    df_all['ville'].str.contains(search, case=False, na=False)
                )
                df_filtered = df_all[mask]
            else:
                df_filtered = df_all

            if df_filtered.empty:
                st.warning("Aucun résultat pour cette recherche.")
            else:
                st.markdown("##### 📄 Détail des fournisseurs")
                st.dataframe(
                    df_filtered,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "id": st.column_config.NumberColumn("ID", width="small"),
                        "nom": st.column_config.TextColumn("Nom", width="medium"),
                        "telephone": st.column_config.TextColumn("Téléphone", width="small"),
                        "ville": st.column_config.TextColumn("Ville", width="small"),
                        "Rccm": st.column_config.TextColumn("RCCM", width="small"),
                        "nui": st.column_config.TextColumn("NUI", width="small"),
                        "adresse": st.column_config.TextColumn("Adresse", width="medium"),
                        "numero_de_compte": st.column_config.TextColumn("Compte / Mobile", width="medium"),
                        "date_ajout": st.column_config.TextColumn("Date ajout", width="small"),
                        "email": st.column_config.TextColumn("Email", width="medium"),
                        "pays": st.column_config.TextColumn("Pays", width="medium"),
                        "code_postal": st.column_config.TextColumn("Code Postal", width="medium"),
                        "adresse_complete": st.column_config.TextColumn("Adresse complète", width="medium"),
                        "tva_intra": st.column_config.TextColumn("TVA Intracommunautaire", width="medium"),
                        "devise_preferee": st.column_config.TextColumn("Devise préférée", width="medium"),
                        "condition_paiement": st.column_config.TextColumn("Condition de paiement", width="medium"),
                        "langue_facture": st.column_config.TextColumn("Langue de facture", width="medium"),
                    }
                )
                st.caption("💡 Utilisez les onglets « Modifier » ou « Supprimer » pour agir sur un fournisseur spécifique.")

    # ============================================================
    # TAB 2 : AJOUT DE FOURNISSEUR
    # ============================================================
    with tab2:
        st.subheader("➕ Ajouter un nouveau fournisseur")
        with st.form("add_f", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            nom = c1.text_input("Nom *")
            tel = c2.text_input("Téléphone *")
            ville = c3.text_input("Ville")
            
            c4, c5, c6 = st.columns(3)
            rccm = c4.text_input("RCCM")
            nui = c5.text_input("NUI")
            adr = c6.text_input("Adresse")
            
            # --- Nouveaux champs ---
            st.subheader("📌 Informations complémentaires")
            col1, col2, col3 = st.columns(3)
            email = col1.text_input("Email")
            pays = col2.text_input("Pays", value="Cameroun")
            code_postal = col3.text_input("Code Postal")
            
            col4, col5, col6 = st.columns(3)
            adresse_complete = col4.text_input("Adresse complète")
            tva_intra = col5.text_input("TVA Intracommunautaire")
            devise_preferee = col6.selectbox("Devise préférée", ["XAF", "EUR", "USD", "GBP"])
            
            col7, col8 = st.columns(2)
            condition_paiement = col7.text_input("Condition de paiement", value="30 jours net")
            langue_facture = col8.selectbox("Langue de facturation", ["fr", "en"])
            # --- Fin des nouveaux champs ---
            
            ndc = st.text_input("Numéro de Compte / Téléphone Mobile Money")
            
            if st.form_submit_button("💾 Enregistrer", use_container_width=True):
                if nom and tel:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO fournisseurs 
                            (nom, telephone, ville, Rccm, adresse, numero_de_compte, nui, 
                            email, pays, code_postal, adresse_complete, tva_intra, 
                            devise_preferee, condition_paiement, langue_facture, date_ajout)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        """, (nom, tel, ville, rccm, adr, ndc, nui, 
                            email, pays, code_postal, adresse_complete, 
                            tva_intra, devise_preferee, condition_paiement, langue_facture))
                        conn.commit()
                    log_action(f"Ajout fournisseur {nom}")
                    st.success("✅ Fournisseur créé avec succès !")
                    st.rerun()
                else:
                    st.error("❌ Le nom et le téléphone sont obligatoires.")

    # ============================================================
    # TAB 3 : MODIFICATION DE FOURNISSEUR
    # ============================================================
    with tab3:
        st.subheader("📝 Modifier un fournisseur existant")
        f_list = fetch_all("SELECT id, nom FROM fournisseurs")
        if f_list:
            dict_edit_f = {f"{f[1]} (ID: {f[0]})": f[0] for f in f_list}
            chosen_f = st.selectbox("Sélectionner le fournisseur à modifier", list(dict_edit_f.keys()))
            id_to_edit = dict_edit_f[chosen_f]

            current_vals = fetch_one(
                "SELECT nom, telephone, ville, Rccm, adresse, numero_de_compte, nui, email, pays, code_postal, adresse_complete, tva_intra, devise_preferee, condition_paiement, langue_facture FROM fournisseurs WHERE id=%s",
                (id_to_edit,)
            )

            with st.form("edit_f_form"):
                e1, e2, e3 = st.columns(3)
                m_nom = e1.text_input("Nom", value=current_vals[0])
                m_tel = e2.text_input("Téléphone", value=current_vals[1])
                m_ville = e3.text_input("Ville", value=current_vals[2] or "")
                
                e4, e5, e6 = st.columns(3)
                m_rccm = e4.text_input("RCCM", value=current_vals[3] or "")
                m_nui = e5.text_input("NUI", value=current_vals[6] or "")
                m_adr = e6.text_input("Adresse", value=current_vals[4] or "")
                
                e7, e8, e9, e10 = st.columns(4)
                m_ndc = e7.text_input("Numéro de Compte", value=current_vals[5] or "")
                m_email = e8.text_input("Email", value=current_vals[7] or "")
                m_pays = e9.text_input("Pays", value=current_vals[8] or "")
                m_code_postal = e10.text_input("Code Postal", value=current_vals[9] or "")
                
                e11, e12, e13, e14 = st.columns(4)
                m_adr_complete = e11.text_input("Adresse complète", value=current_vals[10] or "")
                m_tva_intra = e12.text_input("TVA Intracommunautaire", value=current_vals[11] or "")
                m_devise = e13.text_input("Devise préférée", value=current_vals[12] or "")
                m_condition_paiement = e14.text_input("Condition de paiement", value=current_vals[13] or "")
                
                e15 = st.columns(1)[0]
                m_langue_facture = e15.text_input("Langue de facture", value=current_vals[14] or "")

                if st.form_submit_button("💾 Sauvegarder les modifications", use_container_width=True):
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE fournisseurs SET nom=%s, telephone=%s, ville=%s, Rccm=%s, adresse=%s, numero_de_compte=%s, nui=%s, email=%s, pays=%s, code_postal=%s, adresse_complete=%s, tva_intra=%s, devise_preferee=%s, condition_paiement=%s, langue_facture=%s WHERE id=%s",
                            (m_nom, m_tel, m_ville, m_rccm, m_adr, m_ndc, m_nui, m_email, m_pays, m_code_postal, m_adr_complete, m_tva_intra, m_devise, m_condition_paiement, m_langue_facture, id_to_edit)
                        )
                        conn.commit()
                    log_action(f"Modification fournisseur ID {id_to_edit}")
                    st.success("✅ Modifications enregistrées !")
                    st.rerun()
        else:
            st.info("Aucun fournisseur à modifier.")

    # ============================================================
    # TAB 4 : COMPTES DE PAIEMENT
    # ============================================================
    with tab4:
        st.subheader("💳 Liaison de comptes bancaires et mobiles de secours")
        f_list = fetch_all("SELECT id, nom FROM fournisseurs")
        
        if not f_list:
            st.info("Aucun fournisseur enregistré. Créez-en un dans l'onglet 'Ajouter' d'abord.")
        else:
            dict_comptes_f = {f"{f[1]} (ID: {f[0]})": f[0] for f in f_list}
            chosen_f_for_accounts = st.selectbox("Sélectionner le fournisseur à équiper :", list(dict_comptes_f.keys()))
            id_f_selected = dict_comptes_f[chosen_f_for_accounts]
            
            st.divider()

            col_left, col_right = st.columns(2)

            with col_left:
                st.markdown("##### ➕ Lier un nouveau compte")

                if "selected_type" not in st.session_state:
                    st.session_state.selected_type = "Mobile Money"

                with st.form("form_add_payment_acc", clear_on_submit=False):
                    type_c = st.selectbox(
                        "Type de compte",
                        ["Mobile Money", "Bancaire"],
                        index=0 if st.session_state.selected_type == "Mobile Money" else 1,
                        key="type_select"
                    )
                    st.session_state.selected_type = type_c

                    inst = ""
                    num_c = ""
                    titulaire_c = ""

                    if type_c == "Mobile Money":
                        inst = st.selectbox("Opérateur", ["MTN MoMo", "Orange Money", "Wave"])
                        num_c = st.text_input("Numéro de Téléphone", placeholder="Ex: 677... ou 650...")
                        titulaire_c = st.text_input("Nom officiel du titulaire", placeholder="Ex: ETS FRIENDS TRADING")
                    elif type_c == "Bancaire":
                        inst = st.text_input("Nom de la Banque", placeholder="Ex: Afriland First Bank, SGC, CCA...")
                        num_c = st.text_input("Numéro de compte", placeholder="Ex: RIB")
                        titulaire_c = st.text_input("Nom officiel du titulaire", placeholder="Ex: ETS FRIENDS TRADING")

                    submit_payment = st.form_submit_button("💾 Enregistrer ce moyen de paiement", use_container_width=True)

                    if submit_payment:
                        if not num_c or not titulaire_c or not inst:
                            st.error("Tous les champs sont obligatoires.")
                        else:
                            try:
                                with conn.cursor() as cur:
                                    cur.execute(
                                        """
                                        INSERT INTO comptes_fournisseurs (id_fournisseur, type_compte, nom_institution, numero_compte, titulaire)
                                        VALUES (%s, %s, %s, %s, %s)
                                        """,
                                        (id_f_selected, type_c, inst, num_c, titulaire_c)
                                    )
                                    conn.commit()
                                log_action(f"Nouveau moyen de paiement {type_c} ({inst}) lié au fournisseur ID {id_f_selected}")
                                st.success("✅ Moyen de paiement enregistré !")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Erreur lors de l'enregistrement : {e}")

            with col_right:
                st.markdown("##### 📋 Comptes de paiement actifs")
                try:
                    df_comptes = get_dataframe_from_query("""
                        SELECT id, type_compte AS "Type", nom_institution AS "Institution", numero_compte AS "Numéro / Tél", titulaire AS "Titulaire"
                        FROM comptes_fournisseurs
                        WHERE id_fournisseur = %s
                    """, (id_f_selected,))

                    if df_comptes.empty:
                        st.info("Ce fournisseur utilise uniquement son compte principal.")
                    else:
                        st.dataframe(df_comptes.drop(columns=['id']), use_container_width=True, hide_index=True)
                        
                        st.markdown("---")
                        st.markdown("**🗑️ Supprimer un moyen de paiement :**")
                        
                        dict_del_acc = {f"{row[1]} ({row[2]}) - {row[3]}": row[0] for row in df_comptes.values.tolist()}
                        acc_to_del = st.selectbox("Sélectionner le compte à détruire", list(dict_del_acc.keys()), key="del_acc_selectbox")
                        
                        if st.button("🗑️ Supprimer ce compte définitivement", type="primary", use_container_width=True):
                            id_acc_del = dict_del_acc[acc_to_del]
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM comptes_fournisseurs WHERE id = %s", (id_acc_del,))
                                conn.commit()
                            log_action(f"Moyen de paiement ID {id_acc_del} supprimé")
                            st.success("Compte de paiement retiré avec succès !")
                            st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la lecture des comptes : {e}")

    # ============================================================
    # TAB 5 : SUPPRESSION DE FOURNISSEUR
    # ============================================================
    with tab5:
        st.subheader("🗑️ Supprimer un fournisseur")
        f_list = fetch_all("SELECT id, nom FROM fournisseurs")
        if f_list:
            dict_del_f = {f"{f[1]} (ID: {f[0]})": f[0] for f in f_list}
            to_del = st.selectbox("Sélectionner le fournisseur à supprimer", list(dict_del_f.keys()))
            id_to_del = dict_del_f[to_del]

            if st.button("❌ Supprimer définitivement", type="primary", key="del_f_final_btn", use_container_width=True):
                row = fetch_one("SELECT COUNT(*) FROM achats WHERE id_fournisseur=%s", (id_to_del,))
                has_achats = row[0] if row else 0
                if has_achats > 0:
                    st.error("⚠️ Sécurité : Impossible de supprimer ce fournisseur car il possède des lots de cacao enregistrés.")
                else:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM fournisseurs WHERE id=%s", (id_to_del,))
                        conn.commit()
                    log_action(f"Suppression fournisseur ID {id_to_del}")
                    st.success("Fournisseur supprimé !")
                    st.rerun()
        else:
            st.info("Aucun fournisseur à supprimer.")

    # ============================================================
    # TAB 6 : HISTORIQUE DES LIVRAISONS & CONTRATS
    # ============================================================
    with tab6:
        st.subheader("📦 Historique des lots et contrats livrés")
        f_list = fetch_all("SELECT id, nom FROM fournisseurs")

        if not f_list:
            st.info("Aucun fournisseur enregistré.")
        else:
            dict_hist_f = {f"{f[1]} (ID: {f[0]})": f[0] for f in f_list}
            chosen_f_hist = st.selectbox(
                "Sélectionner le fournisseur à consulter :", 
                list(dict_hist_f.keys()), 
                key="hist_f_select"
            )
            id_f_hist = dict_hist_f[chosen_f_hist]

            st.divider()

            try:
                # Utilisation de get_dataframe_from_query avec paramètres
                df_achats = get_dataframe_from_query("""
                    SELECT 
                        id AS "ID Lot",
                        date AS "Date Livraison",
                        numero_de_lot AS "Code Lot / Contrat",
                        poids_net AS "Poids Net (kg)",
                        prix_unitaire AS "Prix / kg",
                        total AS "Montant Total",
                        statut AS "Statut"
                    FROM achats 
                    WHERE id_fournisseur = %s
                    ORDER BY id DESC
                """, (id_f_hist,))

                if not df_achats.empty:
                    for col in ['Poids Net (kg)', 'Prix / kg', 'Montant Total']:
                        df_achats[col] = pd.to_numeric(df_achats[col], errors='coerce').fillna(0.0)

                    total_lots = len(df_achats)
                    total_poids = df_achats["Poids Net (kg)"].sum()
                    total_montant = df_achats["Montant Total"].sum()

                    kpi1, kpi2, kpi3 = st.columns(3)
                    kpi1.metric("📦 Lots Livrés", f"{total_lots}")
                    kpi2.metric("⚖️ Volume Cumulé", f"{total_poids:,.0f} kg".replace(",", " "))
                    kpi3.metric("💰 Valeur Totale", f"{total_montant:,.0f} FCFA".replace(",", " "))

                    st.markdown("##### 📄 Détail des opérations")
                    st.dataframe(
                        df_achats,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "Poids Net (kg)": st.column_config.NumberColumn(format="%.2f kg"),
                            "Prix / kg": st.column_config.NumberColumn(format="%.2f FCFA"),
                            "Montant Total": st.column_config.NumberColumn(format="%.2f FCFA")
                        }
                    )
                else:
                    st.warning("⚠️ Aucun lot de cacao ou contrat enregistré pour ce fournisseur.")

            except Exception as e:
                st.error(f"Erreur lors de la récupération de l'historique des achats : {e}")

elif choix == "👥 Clients":
    st.title("👥 Répertoire des Clients Internationaux")
    tab1, tab2, tab3 = st.tabs(["➕ Ajouter", "📝 Modifier", "🗑️ Supprimer"])

    # --- TAB 1 : AJOUTER ---
    with tab1:
        with st.form("add_c", clear_on_submit=True):
            st.subheader("📝 Informations Générales")
            c1, c2, c3, c4 = st.columns(4)
            nom = c1.text_input("Nom de l'Entreprise / Client *")
            email = c2.text_input("Email *")
            tel = c3.text_input("Téléphone *")
            langue = c4.selectbox("Langue Facture", ["fr", "en"], help="Détermine la langue du PDF généré")

            st.subheader("📍 Localisation")
            c5, c6, c7, c8 = st.columns(4)
            pays = c5.text_input("Pays", value="Cameroun")
            ville = c6.text_input("Ville")
            code_postal = c7.text_input("Zip / Code Postal")
            adresse_complete = c8.text_input("Adresse complète (Rue, Bâtiment)")

            st.subheader("⚖️ Informations Légales & Financières")
            c9, c10, c11, c12 = st.columns(4)
            devise = c9.selectbox("Devise de facturation", ["XAF", "EUR", "USD", "GBP"])
            condition = c10.text_input("Condition de paiement", value="30 jours net")
            rccm = c11.text_input("RCCM / Numéro d'Enregistrement")
            nui = c12.text_input("NUI / Tax ID / TVA Intra")

            st.info("💡 L'email et le NUI/Tax ID sont cruciaux pour les expéditions internationales.")
            
            if st.form_submit_button("✅ Enregistrer le Client", use_container_width=True):
                if nom and tel and email:
                    with conn.cursor() as cur:
                        cur.execute(
                            """INSERT INTO clients 
                            (nom, email, telephone, ville, rccm, nui, adresse_complete, pays, code_postal, devise_preferee, condition_paiement, langue_facture, date_ajout) 
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (nom, email, tel, ville, rccm, nui, adresse_complete, pays, code_postal, devise, condition, langue, datetime.now().strftime("%Y-%m-%d"))
                        )
                        conn.commit()
                    log_action(f"Ajout client international: {nom}")
                    st.success(f"Client {nom} enregistré avec succès !")
                    st.rerun()
                else:
                    st.error("❌ Le Nom, l'Email et le Téléphone sont obligatoires.")

    # --- TAB 2 : MODIFIER ---
    with tab2:
        c_list = fetch_all("SELECT id, nom FROM clients")
        if c_list:
            dict_edit_c = {f"{c[1]} (ID: {c[0]})": c[0] for c in c_list}
            chosen_c = st.selectbox("Sélectionner le client à modifier", list(dict_edit_c.keys()))
            id_to_edit = dict_edit_c[chosen_c]

            current_vals = fetch_one(
                """SELECT nom, email, telephone, ville, rccm, nui, adresse_complete, pays, 
                          code_postal, devise_preferee, condition_paiement, langue_facture 
                   FROM clients WHERE id=%s""",
                (id_to_edit,)
            )

            with st.form("edit_c_form"):
                st.subheader("📝 Informations Générales")
                e1, e2, e3, e4 = st.columns(4)
                m_nom = e1.text_input("Nom", value=current_vals[0] or "")
                m_email = e2.text_input("Email", value=current_vals[1] or "")
                m_tel = e3.text_input("Téléphone", value=current_vals[2] or "")
                
                langue_idx = 0 if current_vals[11] not in ["fr", "en"] else ["fr", "en"].index(current_vals[11])
                m_langue = e4.selectbox("Langue facture", ["fr", "en"], index=langue_idx)

                st.subheader("📍 Localisation")
                e5, e6, e7, e8 = st.columns(4)
                m_pays = e5.text_input("Pays", value=current_vals[7] or "Cameroun")
                m_ville = e6.text_input("Ville", value=current_vals[3] or "")
                m_code_postal = e7.text_input("Code postal", value=current_vals[8] or "")
                m_adresse_complete = e8.text_input("Adresse complète", value=current_vals[6] or "")

                st.subheader("⚖️ Informations Légales & Financières")
                e9, e10, e11, e12 = st.columns(4)
                
                devise_opts = ["XAF", "EUR", "USD", "GBP"]
                devise_idx = 0 if current_vals[9] not in devise_opts else devise_opts.index(current_vals[9])
                m_devise = e9.selectbox("Devise préférée", devise_opts, index=devise_idx)
                
                m_condition = e10.text_input("Condition de paiement", value=current_vals[10] or "30 jours net")
                m_rccm = e11.text_input("RCCM / Numéro d'Enregistrement", value=current_vals[4] or "")
                m_nui = e12.text_input("NUI / Tax ID / TVA Intra", value=current_vals[5] or "")

                if st.form_submit_button("🔄 Mettre à jour le Client", use_container_width=True):
                    with conn.cursor() as cur:
                        cur.execute(
                            """UPDATE clients SET 
                               nom=%s, email=%s, telephone=%s, ville=%s, rccm=%s, nui=%s, adresse_complete=%s, 
                               pays=%s, code_postal=%s, devise_preferee=%s, condition_paiement=%s, langue_facture=%s 
                               WHERE id=%s""",
                            (m_nom, m_email, m_tel, m_ville, m_rccm, m_nui, m_adresse_complete, 
                             m_pays, m_code_postal, m_devise, m_condition, m_langue, id_to_edit)
                        )
                        conn.commit()
                    log_action(f"Modification client ID {id_to_edit}")
                    st.success("✅ Client mis à jour avec succès !")
                    st.rerun()
        else:
            st.info("Aucun client enregistré.")

    # --- TAB 3 : SUPPRIMER ---
    with tab3:
        c_list = fetch_all("SELECT id, nom FROM clients")
        if c_list:
            dict_del_c = {f"{c[1]} (ID: {c[0]})": c[0] for c in c_list}
            to_del = st.selectbox("Sélectionner le client à supprimer", list(dict_del_c.keys()))
            id_to_del = dict_del_c[to_del]

            if st.button("❌ Supprimer définitivement", type="primary"):
                row = fetch_one("SELECT COUNT(*) FROM ventes WHERE id_client=%s", (id_to_del,))
                has_ventes = row[0] if row else 0
                if has_ventes > 0:
                    st.error("⚠️ Impossible de supprimer : ce client possède des factures de ventes.")
                else:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM clients WHERE id=%s", (id_to_del,))
                        conn.commit()
                    log_action(f"Suppression client ID {id_to_del}")
                    st.success("✅ Client supprimé !")
                    st.rerun()
        else:
            st.info("Aucun client à supprimer.")

    st.divider()
    st.subheader("📊 Base de données Clients")
    df_clients = get_dataframe_from_query(
        "SELECT id, nom as Nom, email as Email, pays as Pays, devise_preferee as Devise, langue_facture as Langue FROM clients ORDER BY id DESC"
    )
    st.dataframe(df_clients, use_container_width=True)
    
elif choix == "🏗️ Prestataires & Transitaires":
    st.title("🏗️ Prestataires & Transitaires")
    t1, t2 = st.tabs(["🏢 Prestataires", "🚢 Transitaires"])

    def gerer_p_t(table_name, tab_object):
        with tab_object:
            # Récupération des éléments avec un curseur local
            items = fetch_all(f"SELECT id, nom FROM {table_name}")
            sub1, sub2, sub3 = st.tabs(["➕ Ajouter", "📝 Modifier", "🗑️ Supprimer"])

            with sub1:
                with st.form(f"add_{table_name}"):
                    nom = st.text_input("Nom *")
                    c1, c2 = st.columns(2)
                    nui = c1.text_input("NUI")
                    rccm = c2.text_input("RCCM")
                    c3, c4 = st.columns(2)
                    tel = c3.text_input("Telephone")
                    bp = c4.text_input("Boite Postale (BP)")
                    if st.form_submit_button("Enregistrer"):
                        if nom:
                            with conn.cursor() as cur:
                                cur.execute(
                                    f"INSERT INTO {table_name} (nom, nui, rccm, telephone, bp, date_ajout) VALUES (%s,%s,%s,%s,%s,%s)",
                                    (nom, nui, rccm, tel, bp, datetime.now().strftime("%d/%m/%Y"))
                                )
                                conn.commit()
                            log_action(f"Ajout {table_name} {nom}")
                            st.success("Ajouté !")
                            st.rerun()
                        else:
                            st.error("Le nom est obligatoire.")

            with sub2:
                if items:
                    dict_items = {f"{i[1]} (ID: {i[0]})": i[0] for i in items}
                    chosen_item = st.selectbox("Selectionner l'element a modifier", list(dict_items.keys()), key=f"sel_mod_{table_name}")
                    id_m = dict_items[chosen_item]
                    curr = fetch_one(f"SELECT nom, nui, rccm, telephone, bp FROM {table_name} WHERE id=%s", (id_m,))

                    with st.form(f"form_mod_{table_name}"):
                        m_nom = st.text_input("Nom", value=curr[0] if curr else "")
                        m_nui = st.text_input("NUI", value=curr[1] if curr else "")
                        m_rccm = st.text_input("RCCM", value=curr[2] if curr else "")
                        m_tel = st.text_input("Telephone", value=curr[3] if curr else "")
                        m_bp = st.text_input("BP", value=curr[4] if curr else "")
                        if st.form_submit_button("Appliquer les modifications"):
                            with conn.cursor() as cur:
                                cur.execute(
                                    f"UPDATE {table_name} SET nom=%s, nui=%s, rccm=%s, telephone=%s, bp=%s WHERE id=%s",
                                    (m_nom, m_nui, m_rccm, m_tel, m_bp, id_m)
                                )
                                conn.commit()
                            log_action(f"Modification {table_name} ID {id_m}")
                            st.success("Modifié !")
                            st.rerun()
                else:
                    st.info("Aucune donnée disponible.")

            with sub3:
                if items:
                    dict_del = {f"{i[1]} (ID: {i[0]})": i[0] for i in items}
                    chosen_del = st.selectbox("Selectionner l'element a supprimer", list(dict_del.keys()), key=f"sel_del_{table_name}")
                    id_d = dict_del[chosen_del]
                    if st.button("❌ Supprimer", type="primary", key=f"btn_del_{table_name}"):
                        with conn.cursor() as cur:
                            cur.execute(f"DELETE FROM {table_name} WHERE id=%s", (id_d,))
                            conn.commit()
                        log_action(f"Suppression {table_name} ID {id_d}")
                        st.success("Supprimé !")
                        st.rerun()
                else:
                    st.info("Aucune donnée à supprimer.")

            st.divider()
            # Affichage du tableau avec un curseur local
            df_res = get_dataframe_from_query(f"SELECT id, nom as Nom, nui as NUI, rccm as RCCM, telephone as Tel, bp as BP FROM {table_name}")
            st.dataframe(df_res, use_container_width=True)

    gerer_p_t("prestataires", t1)
    gerer_p_t("transitaires", t2)
    
elif choix == "📦 Mouvements de Stock":
    
    # ---------------------------------------------------------
    # EN-TÊTE
    # ---------------------------------------------------------
    st.title("📦 Gestion des Mouvements de Stock")
    st.caption("Suivez en temps réel les entrées, sorties et transferts de marchandises.")
    st.divider()

    # Récupération de la liste des magasins (une seule fois)
    magasins = [row[0] for row in fetch_all("SELECT nom FROM magasins")]

    # ---------------------------------------------------------
    # 1. FORMULAIRE DE SAISIE RAPIDE (dans un expandeur)
    # ---------------------------------------------------------
    with st.expander("✏️ Saisir un nouveau mouvement", expanded=False):
        with st.form("form_mouvement_stock", clear_on_submit=True):
            st.markdown("#### Informations du mouvement")
            col1, col2, col3 = st.columns(3)
            type_mvt = col1.selectbox("Type de mouvement *", ["Entrée", "Sortie", "Transfert"])
            magasin_dest = col2.selectbox("Magasin concerné *", magasins)
            
            # Si transfert, on ajoute un champ source
            if type_mvt == "Transfert":
                # Liste des magasins sources (excluant la destination)
                sources = [m for m in magasins if m != magasin_dest]
                magasin_source = col3.selectbox("Magasin source *", sources)
            else:
                magasin_source = None
                col3.text("(non applicable)")
            
            col4, col5, col6 = st.columns(3)
            qte = col4.number_input("Quantité (kg) *", min_value=0.01, step=10.0)
            fournisseur = col5.text_input("Fournisseur (ex: nom, adresse)")
            origine = col6.text_input("Origine / Provenance (ex: fournisseur, client)")
            
            commentaire = st.text_area("Commentaire / Motif", placeholder="Précisez le contexte du mouvement...")
            
            submit_mvt = st.form_submit_button("✅ Enregistrer le mouvement", type="primary", use_container_width=True)
            
            if submit_mvt:
                if not magasin_dest:
                    st.error("Veuillez sélectionner un magasin.")
                elif type_mvt == "Transfert" and not magasin_source:
                    st.error("Veuillez sélectionner un magasin source pour le transfert.")
                elif qte <= 0:
                    st.error("La quantité doit être positive.")
                else:
                    date_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        with conn.cursor() as cur:
                            if type_mvt == "Entrée":
                                cur.execute("""
                                    INSERT INTO stock (date, type, quantite_kg, origine, magasin_destination, fournisseur, id_contrat, commentaire)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                """, (date_now, "Entrée", qte, origine, magasin_dest, fournisseur, None, commentaire))
                            elif type_mvt == "Sortie":
                                # Vérification du stock disponible
                                cur.execute("""
                                    SELECT COALESCE(SUM(CASE WHEN type='Entrée' THEN quantite_kg ELSE -quantite_kg END), 0)
                                    FROM stock WHERE magasin_destination = %s
                                """, (magasin_dest,))
                                stock_dispo = cur.fetchone()[0]
                                if stock_dispo < qte:
                                    st.error(f"Stock insuffisant dans {magasin_dest}. Disponible : {stock_dispo:.2f} kg")
                                    st.stop()
                                else:
                                    cur.execute("""
                                        INSERT INTO stock (date, type, quantite_kg, origine, magasin_destination, fournisseur, id_contrat, commentaire)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                    """, (date_now, "Sortie", qte, origine, magasin_dest, fournisseur, None, commentaire))
                            elif type_mvt == "Transfert":
                                # Vérification du stock source
                                cur.execute("""
                                    SELECT COALESCE(SUM(CASE WHEN type='Entrée' THEN quantite_kg ELSE -quantite_kg END), 0)
                                    FROM stock WHERE magasin_destination = %s
                                """, (magasin_source,))
                                stock_source = cur.fetchone()[0]
                                if stock_source < qte:
                                    st.error(f"Stock insuffisant dans {magasin_source}. Disponible : {stock_source:.2f} kg")
                                    st.stop()
                                else:
                                    # Sortie du magasin source
                                    cur.execute("""
                                        INSERT INTO stock (date, type, quantite_kg, origine, magasin_destination, fournisseur, id_contrat, commentaire)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                    """, (date_now, "Sortie", qte, f"Transfert vers {magasin_dest}", magasin_source, fournisseur, None, f"Transfert vers {magasin_dest} - {commentaire}"))
                                    # Entrée dans le magasin destination
                                    cur.execute("""
                                        INSERT INTO stock (date, type, quantite_kg, origine, magasin_destination, fournisseur, id_contrat, commentaire)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                                    """, (date_now, "Entrée", qte, f"Transfert depuis {magasin_source}", magasin_dest, fournisseur, None, f"Transfert depuis {magasin_source} - {commentaire}"))
                            conn.commit()
                            log_action(f"Mouvement stock : {type_mvt} de {qte} kg - {magasin_dest}")
                            st.success("✅ Mouvement enregistré avec succès !")
                            st.rerun()
                    except Exception as e:
                        conn.rollback()
                        st.error(f"Erreur lors de l'enregistrement : {e}")

    st.divider()

    # ---------------------------------------------------------
    # 2. ÉTAT DES STOCKS : Jauges + Détail des lots
    # ---------------------------------------------------------
    st.subheader("📊 État des stocks par magasin")

    # =========================================================
    # 2.1 Jauges de capacité par magasin
    # =========================================================
    query_magasins = """
        SELECT
            m.nom AS magasin,
            COALESCE(m.capacite_kg, 0) AS capacite,
            COALESCE((
                SELECT SUM(
                    CASE
                        WHEN s.type = 'Entrée' THEN s.quantite_kg
                        WHEN s.type = 'Sortie' THEN -s.quantite_kg
                        ELSE 0
                    END
                )
                FROM stock s
                WHERE s.magasin_destination = m.nom
            ), 0) AS stock_actuel
        FROM magasins m
        ORDER BY m.nom
    """

    df_etat = get_dataframe_from_query(query_magasins)

    # Sécurité : vérifier que la requête a bien retourné les colonnes
    if not df_etat.empty:

        df_etat.columns = [
            str(c).strip().lower()
            for c in df_etat.columns
        ]

        colonnes_requises = {
            "magasin",
            "capacite",
            "stock_actuel"
        }

        colonnes_manquantes = (
            colonnes_requises - set(df_etat.columns)
        )

        if colonnes_manquantes:

            st.error(
                "❌ Colonnes manquantes dans df_etat : "
                + ", ".join(sorted(colonnes_manquantes))
            )

            st.write(
                "Colonnes reçues :",
                df_etat.columns.tolist()
            )

        else:

            cols_jauges = st.columns(
                min(len(df_etat), 4)
            )

            for idx, row in df_etat.iterrows():

                with cols_jauges[idx % 4]:

                    cap_kg = pd.to_numeric(
                        row["capacite"],
                        errors="coerce"
                    )

                    cap_kg = (
                        0.0
                        if pd.isna(cap_kg)
                        else float(cap_kg)
                    )

                    stock_actuel = pd.to_numeric(
                        row["stock_actuel"],
                        errors="coerce"
                    )

                    stock_actuel = (
                        0.0
                        if pd.isna(stock_actuel)
                        else float(stock_actuel)
                    )

                    magasin_nom = str(
                        row["magasin"]
                    )

                    if cap_kg > 0:

                        percent = max(
                            0.0,
                            min(
                                stock_actuel / cap_kg,
                                1.0
                            )
                        )

                        if percent > 0.90:
                            statut = "🔴 Rempli"
                        elif percent > 0.60:
                            statut = "🟡 Modéré"
                        else:
                            statut = "🟢 Espace disponible"

                        st.metric(
                            f"🏢 {magasin_nom}",
                            f"{stock_actuel:,.0f} kg"
                        )

                        st.progress(percent)

                        st.caption(
                            f"{statut} "
                            f"({cap_kg:,.0f} kg max)"
                        )

                    else:

                        st.metric(
                            f"🏢 {magasin_nom}",
                            f"{stock_actuel:,.0f} kg"
                        )

                        st.caption(
                            "Capacité non définie"
                        )

    st.divider()


    # =========================================================
    # 2.2 DÉTAIL DES LOTS EN STOCK
    # =========================================================
    st.subheader("📋 Détail des lots en stock")

    query_detail = """
        SELECT
            a.id AS "id_achat",
            a.numero_de_lot AS "Lot",
            TO_CHAR(
                a.date,
                'YYYY-MM-DD HH24:MI'
            ) AS "Date_Reception",
            f.nom AS "Fournisseur",
            s.numero_camion AS "Camion",
            s.provenance AS "Provenance",
            a.nombre_de_sacs AS "Sacs",
            a.poids_brut AS "Poids_Brut",
            a.poids_net AS "Poids_Net",
            s.refaction AS "Refaction",
            a.poids_net_paye AS "Poids_Net_Payable",
            m.nom AS "Magasin",
            a.statut AS "Statut_Facturation",
            aq.taux_humidite AS "Humidite",
            aq.statut_qualite AS "Qualite",
            s.quantite_kg AS "Quantite_Stock"
        FROM stock s
        JOIN achats a
            ON s.id_achat = a.id
        JOIN fournisseurs f
            ON a.id_fournisseur = f.id
        LEFT JOIN analyses_qualite aq
            ON a.id = aq.id_achat
        LEFT JOIN magasins m
            ON s.magasin_destination = m.nom
        WHERE s.type = 'Entrée'
        AND s.quantite_kg > 0
        ORDER BY a.date DESC
    """

    df_detail = get_dataframe_from_query(query_detail)


    if df_detail.empty:
        st.info("Aucun lot en stock pour le moment.")
    else:
        # Filtres
        col_f1, col_f2, col_f3 = st.columns(3)
        magasins_list = df_detail['Magasin'].dropna().unique().tolist()
        magasin_filter = col_f1.selectbox("🏢 Filtrer par magasin", ["Tous"] + magasins_list, key="stock_mvt_magasin_filter")
        fournisseurs_list = df_detail['Fournisseur'].unique().tolist()
        fourn_filter = col_f2.selectbox("🏢 Filtrer par fournisseur", ["Tous"] + fournisseurs_list, key="stock_mvt_fournisseur_filter")
        search = col_f3.text_input("🔍 Recherche (lot, camion, provenance)", "", key="stock_mvt_search")

        # Application des filtres
        df_filtre = df_detail.copy()
        if magasin_filter != "Tous":
            df_filtre = df_filtre[df_filtre['Magasin'] == magasin_filter]
        if fourn_filter != "Tous":
            df_filtre = df_filtre[df_filtre['Fournisseur'] == fourn_filter]
        if search:
            mask = (
                df_filtre['Lot'].str.contains(search, case=False, na=False) |
                df_filtre['Camion'].str.contains(search, case=False, na=False) |
                df_filtre['Provenance'].str.contains(search, case=False, na=False)
            )
            df_filtre = df_filtre[mask]

        if df_filtre.empty:
            st.warning("Aucun résultat pour ces critères.")
        else:
            # Métriques
            total_kgs = df_filtre['Poids_Net_Payable'].sum()
            total_sacs = df_filtre['Sacs'].sum()
            total_lots = len(df_filtre)
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("📦 Lots en stock", total_lots)
            col_m2.metric("⚖️ Poids total payable", f"{total_kgs:,.2f} kg")
            col_m3.metric("🛍️ Nombre total de sacs", f"{total_sacs:,.0f}")

            st.divider()

            # Affichage du tableau
            st.dataframe(
                df_filtre,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id_achat": st.column_config.NumberColumn("ID", width="small"),
                    "Lot": st.column_config.TextColumn("Lot"),
                    "Date_Reception": st.column_config.DatetimeColumn("Date réception", format="DD/MM/YYYY HH:mm"),
                    "Fournisseur": st.column_config.TextColumn("Fournisseur"),
                    "Camion": st.column_config.TextColumn("Camion"),
                    "Provenance": st.column_config.TextColumn("Provenance"),
                    "Sacs": st.column_config.NumberColumn("Sacs", format="%d"),
                    "Poids_Brut": st.column_config.NumberColumn("Poids brut (kg)", format="%.2f"),
                    "Poids_Net": st.column_config.NumberColumn("Poids net (kg)", format="%.2f"),
                    "Refaction": st.column_config.NumberColumn("Réfaction (kg)", format="%.2f"),
                    "Poids_Net_Payable": st.column_config.NumberColumn("Net payable (kg)", format="%.2f"),
                    "Magasin": st.column_config.TextColumn("Magasin"),
                    "Statut_Facturation": st.column_config.TextColumn("Statut facturation"),
                    "Humidite": st.column_config.NumberColumn("Humidité (%)", format="%.1f"),
                    "Qualite": st.column_config.TextColumn("Qualité"),
                    "Quantite_Stock": st.column_config.NumberColumn("Qté en stock (kg)", format="%.2f"),
                }
            )

            # Exports
            col_exp1, col_exp2 = st.columns(2)
            with col_exp1:
                st.download_button(
                    "📥 Exporter CSV",
                    df_filtre.to_csv(index=False).encode('utf-8'),
                    "stock_detaille.csv",
                    "text/csv",
                    use_container_width=True
                )
            with col_exp2:
                try:
                    st.download_button(
                        "📥 Exporter Excel",
                        convertir_df_excel(df_filtre),
                        "stock_detaille.xlsx",
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
                except NameError:
                    pass

    st.divider()            
    # ---------------------------------------------------------
    # 3. HISTORIQUE AVEC FILTRES AVANCÉS
    # ---------------------------------------------------------
    st.subheader("🕒 Historique des mouvements")

    # Filtres
    with st.container(border=True):
        col_f1, col_f2, col_f3, col_f4 = st.columns(4)
        # Récupération des magasins distincts pour le filtre
        magasins_db = [row[0] for row in fetch_all("SELECT DISTINCT magasin_destination FROM stock WHERE magasin_destination IS NOT NULL")]
        magasin_filter = col_f1.selectbox("🏢 Filtrer par magasin", ["Tous"] + magasins_db, key="stock_mvt_historique_magasin_filter")
        type_filter = col_f2.selectbox("🔄 Filtrer par type", ["Tous", "Entrée", "Sortie"])
        date_range = col_f3.date_input("📅 Période", value=(date.today() - timedelta(days=30), date.today()), key="date_range")
        fourn_nom = col_f4.text_input("Filtre par origine/ fournisseur", placeholder="Ex: ETS FRIENDS TRADING")

    # Construction de la requête avec filtres
    query_journal = """
        SELECT id, date, type, quantite_kg, origine, magasin_destination, fournisseur, id_contrat, commentaire
        FROM stock WHERE 1=1
    """
    params = []
    if magasin_filter != "Tous":
        query_journal += " AND magasin_destination = %s"
        params.append(magasin_filter)
    if type_filter != "Tous":
        query_journal += " AND type = %s"
        params.append(type_filter)
    if date_range:
        start_date, end_date = date_range
        query_journal += " AND date >= %s AND date <= %s"
        params.extend([start_date.strftime("%Y-%m-%d 00:00:00"), end_date.strftime("%Y-%m-%d 23:59:59")])
    if fourn_nom:
        query_journal += " AND fournisseur LIKE %s"
        params.append(f"%{fourn_nom}%")
    query_journal += " ORDER BY date DESC"

    df_journal = get_dataframe_from_query(query_journal, params)

    if not df_journal.empty:
        st.dataframe(
            df_journal,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": st.column_config.NumberColumn("ID", help="Identifiant du mouvement"),
                "date": st.column_config.DatetimeColumn("Date & Heure", format="DD/MM/YYYY HH:mm"),
                "type": st.column_config.TextColumn("Type"),
                "quantite_kg": st.column_config.NumberColumn("Quantité", format="%.2f kg"),
                "origine": st.column_config.TextColumn("Origine"),
                "magasin_destination": st.column_config.TextColumn("Destination"),
                "fournisseur": st.column_config.TextColumn("Fournisseur"),
                "id_contrat": st.column_config.TextColumn("ID Contrat"),
                "commentaire": st.column_config.TextColumn("Remarques")
            }
        )

        # Bouton d'export
        col_exp, _ = st.columns([1, 3])
        col_exp.download_button(
            label="📥 Exporter le journal (CSV)",
            data=df_journal.to_csv(index=False).encode('utf-8'),
            file_name="journal_stock.csv",
            mime="text/csv",
            use_container_width=True
        )

        # Section de suppression/modification (uniquement pour l'admin)
        if st.session_state.role == "Admin":
            st.divider()
            with st.expander("🛠️ Administration des mouvements (Admin)", expanded=False):
                st.warning("⚠️ Supprimer un mouvement peut déséquilibrer les stocks. Utilisez avec précaution.")
                selected_id = st.selectbox("Sélectionner un mouvement par ID", df_journal['id'].tolist(), key="select_mvt_id")
                if st.button("🗑️ Supprimer ce mouvement", type="primary"):
                    try:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM stock WHERE id = %s", (selected_id,))
                            conn.commit()
                            log_action(f"Suppression du mouvement stock ID {selected_id}")
                            st.success(f"✅ Mouvement ID {selected_id} supprimé.")
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")

        # Graphique des flux
    st.divider()
    st.subheader("📈 Évolution des flux sur la période")
    if 'df_journal' in locals() and not df_journal.empty:
        df_journal['date'] = pd.to_datetime(df_journal['date'], errors='coerce')
        df_journal = df_journal.dropna(subset=['date'])
        df_journal['quantite_kg'] = pd.to_numeric(df_journal['quantite_kg'], errors='coerce').fillna(0.0)
        df_flux = (
            df_journal
            .groupby([pd.Grouper(key='date', freq='D'), 'type'])['quantite_kg']
            .sum()
            .unstack()
            .fillna(0)
        )
        if not df_flux.empty:
            fig_flux = go.Figure()
            for colonne in df_flux.columns:
                x_values = df_flux.index.to_pydatetime().tolist()
                y_values = pd.to_numeric(df_flux[colonne], errors='coerce').fillna(0).astype(float).tolist()
                fig_flux.add_trace(go.Scatter(x=x_values, y=y_values, mode='lines+markers', name=str(colonne)))
            fig_flux.update_layout(
                title="Évolution des flux de stock",
                xaxis_title="Date",
                yaxis_title="Quantité (kg)",
                hovermode="x unified",
                height=450,
                margin=dict(l=20, r=20, t=60, b=20)
            )
            st.plotly_chart(fig_flux, use_container_width=True, key="flux_stock_evolution")
        else:
            st.info("Pas assez de données pour le graphique.")
    else:
        st.info("Pas de données pour le graphique.")
# ==============================================================================
# 1. CODE DE L'ONGLET CONTRATS
# ==============================================================================
elif choix == "📝 Contrats":
    
    # EN-TÊTE CLEAN
    st.title("📝 Gestion & Suivi des Contrats")
    st.write("")  # Petit espace

    fournisseurs = fetch_all("SELECT id, nom FROM fournisseurs")

    if not fournisseurs:
        st.warning("⚠️ Veuillez d'abord enregistrer un fournisseur dans la section dédiée.")
        st.stop()

    dict_f = {f[1]: f[0] for f in fournisseurs}

    tab1, tab2, tab3 = st.tabs(["➕ Créer un Contrat", "📋 Suivi & Exécution", "📚 Historique & Archives"])

    # ==========================================================================
    # TAB 1 : CRÉATION D'UN CONTRAT
    # ==========================================================================
    with tab1:
        path_pdf = None
        contrat_genere = False

        try:
            next_id_row = fetch_one("SELECT COALESCE(MAX(id), 0) + 1 FROM contrats")
            next_id = next_id_row[0] if next_id_row else 1
        except Exception:
            next_id = 1
        
        num_c_auto = f"FCC-{datetime.now().strftime('%Y%m%d')}-{next_id:04d}"
        
        magasins_enregistres = fetch_all("SELECT nom FROM magasins")
        lieux_disponibles = [m[0] for m in magasins_enregistres] if magasins_enregistres else ["Douala-PAD-SOGECAF", "Douala"]

        termes_paie = ["100% Livraison", "Avance 50% / 50% Livraison", "Avance 80% / 20% Livraison", "100% à la signature"]

        with st.form("form_contrat", border=True):
            st.subheader("📋 1. Informations Générales")
            col1, col2 = st.columns(2)
            
            f_nom = col1.selectbox("🏢 Fournisseur", list(dict_f.keys()))
            col2.text_input("N° Contrat (Automatique)", value=num_c_auto, disabled=True)
            
            date_c = col1.date_input("📅 Date de signature", value=date.today())
            date_delai = col2.date_input("🚨 Date limite (Échéance)", value=date.today() + timedelta(days=30))

            st.divider()

            st.subheader("💰 2. Logistique & Finances")
            col3, col4 = st.columns(2)
            
            qte = col3.number_input("⚖️ Quantité prévue (kg)", 0.0, step=500.0)
            pu = col4.number_input("💵 Prix unitaire (FCFA/kg)", 0.0, step=50.0)
            
            lieu = col3.selectbox("📍 Lieu de livraison", lieux_disponibles)
            provenance = col4.text_input("🌍 Provenance du cacao (ex: Sud, Centre...)")
            
            termes = st.selectbox("💳 Termes de Paiement", termes_paie)

            st.write("")
            submit = st.form_submit_button("✅ Enregistrer & Générer le Contrat", use_container_width=True, type="primary")

            if submit:
                if qte <= 0 or pu <= 0:
                    st.error("❌ La quantité prévue et le prix unitaire doivent être supérieurs à 0.")
                else:
                    date_c_str = date_c.strftime("%d/%m/%Y")
                    delai_str = date_delai.strftime("%Y-%m-%d") 
                    
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            INSERT INTO contrats
                            (id_fournisseur, numero_contrat, date_signature,
                             lieu_livraison, quantite_prevue,
                             prix_unitaire, delai_livraison, provenance, termes_de_paiement, statut)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, 'Actif')
                            RETURNING id""",
                            (dict_f[f_nom], num_c_auto, date_c_str, lieu, qte, pu, delai_str, provenance, termes)
                        )
                        id_contrat = cur.fetchone()[0]
                        conn.commit()
                    log_action(f"Création contrat {num_c_auto} avec {f_nom}")
                    st.success(f"🎉 Contrat {num_c_auto} enregistré avec succès !")

                    # Formatage PDF
                    path_pdf = generer_contrat_pdf({
                        "num": num_c_auto,
                        "date": date_c_str,
                        "fournisseur": f_nom,
                        "lieu": lieu,
                        "qte": qte,
                        "pu": pu,
                        "delai": date_delai.strftime("%d/%m/%Y"),
                        "provenance": provenance,
                        "termes_de_paiement": termes
                    })
                    contrat_genere = True

                    montant_total = float(qte) * float(pu)

                    # Insertion du contrat dans le circuit de validation
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO documents_generes (type_doc, reference, montant, demandeur, description, statut)
                            VALUES (%s, %s, %s, %s, %s, 'EN_ATTENTE')
                            RETURNING id""", (
                            'contrat',
                            num_c_auto,
                            montant_total,
                            st.session_state.get('username', 'Agent'),
                            f"Contrat Achat avec {f_nom} ({qte} kg × {pu} XAF - Lieu: {lieu}, Provenance: {provenance})"
                        ))
                        conn.commit()

                    log_action(f"Contrat d'achat N°{num_c_auto} soumis pour validation Direction")
                    st.success(f"📥 Contrat N°{num_c_auto} transmis avec succès à la Direction pour validation !")

    # ==========================================================================
    # TAB 2 : SUIVI & EXÉCUTION
    # ==========================================================================
    with tab2:
        query_contrats = """
            SELECT
                c.id, f.nom AS "Fournisseur", c.numero_contrat AS "N° Contrat",
                c.date_signature AS "Date Signature", c.lieu_livraison AS "Lieu Livraison",
                c.quantite_prevue AS "Qte Prévue (kg)", c.prix_unitaire AS "PU",
                c.delai_livraison AS "Délai Livraison", c.provenance AS "Provenance",
                c.termes_de_paiement AS "Termes de Paiement", c.statut AS "Statut BDD",
                COALESCE((
                    SELECT SUM(quantite_kg) FROM achats WHERE numero_contrat = c.numero_contrat
                ), 0) AS "Qte Livrée (kg)"
            FROM contrats c
            JOIN fournisseurs f ON c.id_fournisseur = f.id
            ORDER BY c.id DESC
        """
        df_base = get_dataframe_from_query(query_contrats)

        if df_base.empty:
            st.info("ℹ️ Aucun contrat actif pour le moment.")
        else:
            def calculer_statut(row):
                statut_bdd = row['Statut BDD']
                if statut_bdd == 'Annule':
                    return "❌ Annulé", "Résilié", 0.0
                
                qte_prevue = float(row['Qte Prévue (kg)'])
                qte_livree = float(row['Qte Livrée (kg)'])
                progression = min(qte_livree / qte_prevue, 1.0) if qte_prevue > 0 else 1.0
                
                delai_str = str(row['Délai Livraison'])
                delai_date = None
                for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
                    try:
                        delai_date = datetime.strptime(delai_str, fmt).date()
                        break
                    except ValueError:
                        pass
                
                aujourd_hui = date.today()
                is_depasse = delai_date and (delai_date < aujourd_hui)
                
                if not delai_date:
                    info_temps = "Invalide"
                else:
                    diff = delai_date - aujourd_hui
                    if diff.days < 0:
                        info_temps = f"🚨 -{abs(diff.days)}j"
                    elif diff.days == 0:
                        info_temps = "⏳ Auj."
                    else:
                        info_temps = f"⏳ +{diff.days}j"

                if qte_livree >= qte_prevue:
                    statut_final = "🟢 Soldé"
                elif is_depasse:
                    statut_final = "🔴 En retard"
                elif qte_livree > 0:
                    statut_final = "🔄 En cours"
                else:
                    statut_final = "⏳ Non livré"
                    
                return statut_final, info_temps, progression

            resultats = df_base.apply(calculer_statut, axis=1)
            df_base['Statut'] = [r[0] for r in resultats]
            df_base['Suivi Temps'] = [r[1] for r in resultats]
            df_base['Taux Remplissage'] = [r[2] for r in resultats]
            df_base['Reste à Livrer (kg)'] = (df_base['Qte Prévue (kg)'] - df_base['Qte Livrée (kg)']).clip(lower=0)

            with st.container(border=True):
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Total Contrats", len(df_base))
                k2.metric("🟢 Soldés", len(df_base[df_base['Statut'] == "🟢 Soldé"]))
                k3.metric("🔄 En Cours", len(df_base[df_base['Statut'] == "🔄 En cours"]))
                k4.metric("🚨 En Retard", len(df_base[df_base['Statut'] == "🔴 En retard"]))

            c_f1, c_f2 = st.columns([1, 2], vertical_alignment="center")
            filtre_statut = c_f1.multiselect("Filtrer (Statut)", df_base['Statut'].unique(), default=df_base['Statut'].unique())
            recherche = c_f2.text_input("🔍 Chercher un Contrat / Fournisseur", "").strip().lower()

            df_affiche = df_base[df_base['Statut'].isin(filtre_statut)]
            if recherche:
                df_affiche = df_affiche[
                    df_affiche["N° Contrat"].str.lower().str.contains(recherche, na=False) |
                    df_affiche['Fournisseur'].str.lower().str.contains(recherche, na=False)
                ]

            df_visuel = df_affiche[["N° Contrat", "Fournisseur", "Date Signature", "Taux Remplissage", "Qte Prévue (kg)", "Reste à Livrer (kg)", "Statut", "Suivi Temps"]].copy()
            
            st.dataframe(
                df_visuel,
                column_config={
                    "N° Contrat": st.column_config.TextColumn("Contrat"),
                    "Taux Remplissage": st.column_config.ProgressColumn("Progrès", format="%.1f%%", min_value=0.0, max_value=1.0),
                    "Qte Prévue (kg)": st.column_config.NumberColumn("Cible (kg)", format="%d"),
                    "Reste à Livrer (kg)": st.column_config.NumberColumn("Reste (kg)", format="%d"),
                },
                use_container_width=True, hide_index=True
            )

            with st.expander("🛠️ Actions & Détails d'un contrat", expanded=False):
                col_ex1, col_ex2 = st.columns(2)
                col_ex1.download_button("📥 Exporter CSV", convertir_df_csv(df_affiche), "contrats.csv", "text/csv")
                try:
                    import openpyxl
                    col_ex2.download_button("📥 Exporter Excel", convertir_df_excel(df_affiche), "contrats.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except ImportError:
                    pass
                
                st.divider()
                st.markdown("#### 🔍 Inspecter ou Modifier un Contrat")
                
                select_contrat = st.selectbox(
                    "Sélectionnez le contrat :", df_base.values.tolist(),
                    format_func=lambda x: f"{x[2]} | {x[1]} ({x[5]:,.0f} kg ciblés)"
                )

                if select_contrat:
                    c_id, c_fourn, c_num, c_statut_actuel = select_contrat[0], select_contrat[1], select_contrat[2], select_contrat[10]
                    ligne_c = df_base[df_base['id'] == c_id].iloc[0]

                    st.info(f"**Progression actuelle :** {ligne_c['Qte Livrée (kg)']:,.0f} kg reçus sur {ligne_c['Qte Prévue (kg)']:,.0f} kg ({ligne_c['Statut']})")

                    df_achats_lies = get_dataframe_from_query("""
                        SELECT date AS "Date", quantite_kg AS "Qte (kg)", prix_unitaire AS "Prix", (quantite_kg * prix_unitaire) AS "Total"
                        FROM achats WHERE numero_contrat = %s ORDER BY id DESC
                    """, (c_num,))

                    if df_achats_lies.empty:
                        st.warning("⚠️ Aucun lot physique réceptionné pour ce contrat.")
                    else:
                        st.dataframe(df_achats_lies, use_container_width=True, hide_index=True)

                    col_a1, col_a2 = st.columns(2)
                    if c_statut_actuel == 'Actif':
                        if col_a1.button("❌ Résilier ce Contrat", key=f"annul_{c_id}"):
                            with conn.cursor() as cur:
                                cur.execute("UPDATE contrats SET statut = 'Annule' WHERE id = %s", (c_id,))
                                conn.commit()
                            st.rerun()
                    else:
                        if col_a2.button("🔄 Réactiver ce Contrat", key=f"react_{c_id}"):
                            with conn.cursor() as cur:
                                cur.execute("UPDATE contrats SET statut = 'Actif' WHERE id = %s", (c_id,))
                                conn.commit()
                            st.rerun()

    # ==========================================================================
    # TAB 3 : HISTORIQUE & RÉGÉNÉRATION PDF
    # ==========================================================================
    with tab3:
        query_hist = """
            SELECT 
                c.id,
                c.numero_contrat AS "N° Contrat",
                f.nom AS "Fournisseur",
                c.date_signature AS "Date Signature",
                c.quantite_prevue AS "Quantité (kg)",
                c.prix_unitaire AS "Prix (FCFA)",
                c.statut AS "Statut"
            FROM contrats c
            JOIN fournisseurs f ON c.id_fournisseur = f.id
            ORDER BY c.id DESC
        """
        df_hist = get_dataframe_from_query(query_hist)
        
        if not df_hist.empty:
            st.subheader("📚 Base de données complète")
            st.dataframe(df_hist, use_container_width=True, hide_index=True)
            
            st.write("")
            with st.container(border=True):
                st.subheader("🖨️ Imprimer un Contrat")
                
                liste_contrats = {}
                for _, row in df_hist.iterrows():
                    statut = row['Statut']
                    icone = "⏳" if statut == "EN_ATTENTE" else "✅" if statut == "VALIDE" else "❌"
                    liste_contrats[row['id']] = f"{icone} {row['N° Contrat']} - {row['Fournisseur']} ({statut})"
                
                selected_id = st.selectbox(
                    "Sélectionnez le contrat à réimprimer :",
                    options=list(liste_contrats.keys()),
                    format_func=lambda x: liste_contrats[x]
                )
                
                contrat_row = df_hist[df_hist['id'] == selected_id].iloc[0]
                num_contrat = contrat_row['N° Contrat']
                statut_selectionne = contrat_row['Statut']
                
                pdf_bytes = None
                if statut_selectionne == "VALIDE":
                    res = fetch_one(
                        "SELECT fichier_pdf FROM documents_generes WHERE reference = %s AND type_doc = 'contrat' AND statut = 'VALIDE'",
                        (num_contrat,)
                    )
                    if res and res[0]:
                        pdf_bytes = bytes(res[0])  # ← conversion explicite
                                
                if pdf_bytes:
                    st.success("✅ Document authentifié disponible (avec QR code et code de vérification).")
                    st.download_button(
                        label="📄 Télécharger le Contrat Authentifié",
                        data=pdf_bytes,
                        file_name=f"{num_contrat}_signe.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    if statut_selectionne == "VALIDE":
                        st.warning("⚠️ Le PDF authentifié n'a pas été stocké lors de la validation. Vous pouvez régénérer un brouillon (sans QR code) ou re-valider le contrat.")
                    else:
                        st.info("ℹ️ Ce contrat n'est pas encore validé. Seul un brouillon est disponible.")
                    
                    if st.button("📄 Générer le Brouillon", use_container_width=True):
                        pdf_brut = regenerer_contrat(selected_id)
                        if pdf_brut:
                            st.download_button(
                                label="⬇️ Télécharger le Brouillon",
                                data=pdf_brut,
                                file_name=f"{num_contrat}_brouillon.pdf",
                                mime="application/pdf"
                            )
                        else:
                            st.error("❌ Erreur lors de la génération du brouillon.")
        else:
            st.info("Aucun contrat dans l'historique.")       

elif choix == "🏪 Magasins":
    # En-tête stylisé
    st.markdown("<h1 style='text-align: center; color: #8B4513;'>🏭 Centre Logistique & Entrepôts</h1>", unsafe_allow_html=True)
    st.caption("Gérez les flux de marchandises, générez vos documents de transport et surveillez vos capacités.")
    st.divider()
    
    # --- TABLEAU DE BORD EXPRESS ---
    total_magasins = get_single_value("SELECT COUNT(*) FROM magasins", 0)
    total_stock_entree = get_single_value("SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE type = 'Entrée'", 0)
    total_stock_sortie = get_single_value("SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE type = 'Sortie'", 0)
    stock_physique_total = total_stock_entree - total_stock_sortie
    
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    col_stat1.metric(label="🏗️ Magasins Actifs", value=total_magasins)
    col_stat2.metric(label="📦 Stock Physique Total", value=f"{stock_physique_total:,.0f} kg")
    col_stat3.metric(label="🔄 Rotations (Sorties)", value=f"{total_stock_sortie:,.0f} kg")
    
    st.write("")

    # --- Initialisation de la session pour les documents PDF ---
    if "br_pret" not in st.session_state:
        st.session_state.br_pret = False
        st.session_state.data_br = {}
        st.session_state.pdf_bytes_br = None
        
    if "bl_pret" not in st.session_state:
        st.session_state.bl_pret = False
        st.session_state.data_bl = {}
        st.session_state.pdf_bytes_bl = None
    
    # Création des onglets
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📥 1. RÉCEPTION (BR)", 
        "📤 2. EXPÉDITION (BL)", 
        "📊 3. ÉTAT DES STOCKS", 
        "⚙️ 4. PARAMÈTRES",
        "🧪 UNITE D'ANALYSE"
    ])
    
    # =====================================================================
    # ---- ONGLET 1 : RÉCEPTION (ENTRÉE)
    # =====================================================================
    with tab1:
        st.subheader("📥 Validation des Entrées")

        if st.session_state.get("br_pret") and st.session_state.get("pdf_bytes_br"):
            with st.container(border=True):
                st.success(f"🎉 Réception validée ! Le Bon de Réception N° **{st.session_state['data_br'].get('num_br')}** est prêt à être imprimé.")
                st.download_button(
                    label="🖨️ IMPRIMER LE BON DE RÉCEPTION (BR)",
                    data=st.session_state["pdf_bytes_br"],
                    file_name=f"Bon_Reception_{st.session_state['data_br'].get('num_br')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                    key="dl_br_top"
                )

        # Récupération des magasins
        magasins_liste = fetch_all("SELECT nom FROM magasins")
        liste_noms_magasins = [m[0] for m in magasins_liste] if magasins_liste else []

        # Contrats actifs
        contrats_dispo = fetch_all("""
            SELECT c.id, c.numero_contrat, f.nom, f.id, c.prix_unitaire, c.provenance 
            FROM contrats c 
            JOIN fournisseurs f ON c.id_fournisseur = f.id
            WHERE c.statut IN ('Actif', 'VALIDE') ORDER BY c.id DESC
        """)
        dict_c = {f"Contrat {c[1]} — {c[2]}": c for c in contrats_dispo} if contrats_dispo else {}

        with st.container(border=True):
            if not dict_c:
                st.warning("⚠️ Aucun contrat actif trouvé dans la base.")
            else:
                c_sel = st.selectbox("📌 Sélectionner le Contrat d'origine *", list(dict_c.keys()))
                infos_c = dict_c[c_sel]
                id_du_contrat, ncc, nom_f, id_f, pu_defaut, prov_defaut = infos_c[0], infos_c[1], infos_c[2], infos_c[3], infos_c[4], infos_c[5]

                st.write("---")
                choix_lot = st.radio(
                    "Action sur la marchandise :",
                    ["✨ Ouvrir un NOUVEAU lot", "🔄 Compléter un lot existant"],
                    horizontal=True,
                    key="choix_lot_pesee"
                )

                lots_ouverts = fetch_all("""
                    SELECT numero_de_lot, quantite_kg, nombre_de_sacs 
                    FROM achats WHERE numero_contrat = %s AND statut = 'En attente de facturation'
                """, (ncc,))

                num_lot_final = ""

                if choix_lot == "🔄 Compléter un lot existant":
                    if not lots_ouverts:
                        st.info("💡 Aucun lot en cours pour ce contrat. Création d'un nouveau lot initiée.")
                        choix_lot = "✨ Ouvrir un NOUVEAU lot"
                    else:
                        dict_lots = {f"📦 Lot {l[0]} (Actuel : {l[1]} kg / {l[2]} sacs)": l[0] for l in lots_ouverts}
                        num_lot_final = dict_lots[st.selectbox("Sélectionner le lot à compléter *", list(dict_lots.keys()))]

                with st.form("form_reception_br"):
                    st.markdown("#### ⚖️ Paramètres de Pesée & Logistique")
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    p_brut = c1.number_input("Poids Brut Camion (kg)", min_value=0.0, step=10.0)
                    p_net = c2.number_input("Poids Net Livré (kg) *", min_value=0.0, step=10.0)
                    n_sacs = c3.number_input("Nombre de sacs *", min_value=0, step=1)
                    poids_net_declarer = c4.number_input("Poids Net déclaré", min_value=0.0, step=10.0)
                    ecart_de_poids = poids_net_declarer - p_net
                    st.write(f"**Écart de poids :** {ecart_de_poids} kg")
                    nature_produit = c5.text_input("Nature du Produit *")
                    centre_de_achat = c6.text_input("Centre de l'achat")

                    c7, c8, c9, c10 = st.columns(4)
                    num_camion = c7.text_input("Immatriculation Camion *")
                    chauffeur_nom = c8.text_input("Nom du Chauffeur *")
                    provenance = c9.text_input("Zone de Provenance", value=prov_defaut if prov_defaut else "")
                    mag_dest = st.selectbox("Magasin de déchargement *", liste_noms_magasins) if liste_noms_magasins else None

                    submit_br = st.form_submit_button("📥 Valider la Réception & Générer le BR", use_container_width=True)

                    if submit_br:
                        if p_net <= 0 or n_sacs <= 0 or not mag_dest or not num_camion or not chauffeur_nom:
                            st.error("❌ Veuillez remplir tous les champs obligatoires (*).")
                        else:
                            date_reception = datetime.now().strftime("%Y-%m-%d %H:%M")
                            num_br_genere = f"BR-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

                            if choix_lot == "✨ Ouvrir un NOUVEAU lot":
                                dernier_lot = fetch_one("""
                                    SELECT numero_de_lot FROM achats 
                                    WHERE numero_de_lot LIKE 'LOT-%' 
                                    ORDER BY id DESC LIMIT 1
                                """)
                                if dernier_lot and dernier_lot[0]:
                                    try:
                                        parts = dernier_lot[0].split('-')
                                        if len(parts) == 3:
                                            suffix = int(parts[2]) + 1
                                            num_lot_final = f"LOT-{datetime.now().strftime('%Y%m%d')}-{suffix:04d}"
                                        else:
                                            num_lot_final = f"LOT-{datetime.now().strftime('%Y%m%d')}-0001"
                                    except:
                                        num_lot_final = f"LOT-{datetime.now().strftime('%Y%m%d')}-0001"
                                else:
                                    num_lot_final = f"LOT-{datetime.now().strftime('%Y%m%d')}-0001"

                            with conn.cursor() as cur:
                                if choix_lot == "✨ Ouvrir un NOUVEAU lot":
                                    cur.execute("""
                                        INSERT INTO achats 
                                        (date, numero_de_lot, id_fournisseur, numero_contrat, 
                                        poids_brut, poids_net, nombre_de_sacs, quantite_kg, statut, numero_br)
                                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'En attente de facturation', %s)
                                        RETURNING id
                                    """, (date_reception, num_lot_final, id_f, ncc, 
                                        p_brut, p_net, n_sacs, p_net, num_br_genere))
                                    id_achat = cur.fetchone()[0]
                                else:
                                    row = fetch_one("SELECT id FROM achats WHERE numero_de_lot = %s AND statut = 'En attente de facturation'", (num_lot_final,))
                                    if row:
                                        id_achat = row[0]
                                    else:
                                        cur.execute("""
                                            INSERT INTO achats 
                                            (date, numero_de_lot, id_fournisseur, numero_contrat, 
                                            poids_brut, poids_net, nombre_de_sacs, quantite_kg, statut, numero_br)
                                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'En attente de facturation', %s)
                                            RETURNING id
                                        """, (date_reception, num_lot_final, id_f, ncc, 
                                            p_brut, p_net, n_sacs, p_net, num_br_genere))
                                        id_achat = cur.fetchone()[0]

                                    cur.execute("""
                                        UPDATE achats 
                                        SET poids_brut = poids_brut + %s,
                                            poids_net = poids_net + %s,
                                            quantite_kg = quantite_kg + %s,
                                            nombre_de_sacs = nombre_de_sacs + %s
                                        WHERE numero_de_lot = %s AND statut = 'En attente de facturation'
                                    """, (p_brut, p_net, p_net, n_sacs, num_lot_final))

                                commentaire = f"Réception du lot {num_lot_final} - Contrat {ncc}" 

                                cur.execute("""
                                    INSERT INTO stock (date, type, quantite_kg, origine, fournisseur, id_contrat, magasin_destination, commentaire, id_achat, numero_camion, provenance)
                                    VALUES (%s, 'Entrée', %s, 'Achat', %s, %s, %s, %s, %s, %s, %s)
                                """, (date_reception, p_net, nom_f, id_du_contrat, mag_dest, commentaire, id_achat, num_camion, provenance))

                                conn.commit()

                            data_br = {
                                "num_br": num_br_genere,
                                "date": date_reception,
                                "magasin": mag_dest,
                                "numero_lot": num_lot_final,
                                "fournisseur": nom_f,
                                "provenance": provenance,
                                "poids_brut": p_brut,
                                "poids_net": p_net,
                                "poids_net_declarer": poids_net_declarer,
                                "ecart_de_poids": ecart_de_poids,
                                "sacs": n_sacs,
                                "camion": num_camion,
                                "chauffeur": chauffeur_nom,
                                "numero_contrat": ncc,
                                "nature_produit": nature_produit,
                                "centre_achat": centre_de_achat,
                            }

                            pdf_path_br = generer_bon_reception_pdf(data_br)
                            with open(pdf_path_br, "rb") as f:
                                pdf_bytes = f.read()

                            st.session_state["data_br"] = data_br
                            st.session_state["pdf_bytes_br"] = pdf_bytes
                            st.session_state["br_pret"] = True
                            st.toast("✅ Réception enregistrée avec succès !", icon="🎉")
                            st.rerun()

    # =====================================================================
    # ---- ONGLET 2 : EXPÉDITION (SORTIE)
    # =====================================================================
    with tab2:
        st.subheader("📤 Ordre d'Expédition & Bon de Livraison")
        
        if st.session_state.get("bl_pret") and st.session_state.get("pdf_bytes_bl"):
            with st.container(border=True):
                num_bl_affiches = st.session_state.get("data_bl", {}).get("num_bl", "Généré")
                st.success(f"🎉 Expédition validée ! Le BL N° **{num_bl_affiches}** est prêt.")
                st.download_button(
                    label="🖨️ IMPRIMER LE BORDEREAU DE LIVRAISON (BL)",
                    data=st.session_state["pdf_bytes_bl"],
                    file_name=f"Bordereau_Livraison_{num_bl_affiches}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                    key="dl_bl_top"
                )

        ventes_en_attente = fetch_all("""
            SELECT v.id, v.client_nom, v.quantite_kg, m.nom 
            FROM ventes v
            JOIN magasins m ON v.id_magasin = m.id
            WHERE v.statut_livraison = 'En attente d''expédition'
        """)

        with st.container(border=True):
            if not ventes_en_attente:
                st.success("✅ Super ! Aucune commande en attente d'expédition pour le moment.")
            else:
                dict_ventes = {f"Commande N°{v[0]} : {v[2]} kg pour {v[1]} (Départ : {v[3]})": v for v in ventes_en_attente}
                vente_choisie = st.selectbox("📦 Sélectionner la commande à expédier :", list(dict_ventes.keys()))
                v_data = dict_ventes[vente_choisie]
                id_vente_sel = v_data[0]
                client_sel = v_data[1]
                poids_a_sortir = v_data[2]
                magasin_depart = v_data[3]
                
                with st.form("form_expedition_bl"):
                    st.markdown("#### 📦 1. Quantités et Destination")
                    st.info(f"📍 **Magasin :** {magasin_depart} | 👤 **Client :** {client_sel} | ⚖️ **Poids net vendu :** {poids_a_sortir} kg")
                    
                    col1, col2 = st.columns(2)
                    sacs_sortis = col1.number_input("Nombre de sacs chargés *", min_value=1, step=1)
                    destination = col2.text_input("Lieu de livraison / Usine *", value=client_sel)

                    st.markdown("#### 🔬 2. Analyse de Qualité")
                    col4, col5, col6 = st.columns(3)
                    taux_humidite = col4.number_input("Taux d'humidité (%) *", min_value=0.0, step=0.1, value=7.5)
                    taux_moisissure = col5.number_input("Taux de moisissure (%) *", min_value=0.0, step=0.1, value=1.0)
                    nature_produit = col6.text_input("Nature du Produit", value="CACAO GRADE 1")

                    st.markdown("#### 🚚 3. Détails du Transport")
                    col7, col8 = st.columns(2)
                    camion_bl = col7.text_input("Immatriculation du Camion *")
                    chauffeur_bl = col8.text_input("Nom du chauffeur *")
                    
                    submit_bl = st.form_submit_button("🖨️ Valider la Sortie (Déstocker) & Générer le BL", use_container_width=True)
                    
                    if submit_bl:
                        if not destination or not camion_bl or not chauffeur_bl:
                            st.error("❌ Veuillez remplir tous les champs obligatoires (*).")
                        else:
                            # Vérification du stock disponible
                            row = fetch_one("""
                                SELECT 
                                    (SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE magasin_destination = %s AND type = 'Entrée') -
                                    (SELECT COALESCE(SUM(quantite_kg), 0) FROM stock WHERE magasin_destination = %s AND type = 'Sortie')
                            """, (magasin_depart, magasin_depart))
                            stock_dispo = float(row[0]) if row and row[0] is not None else 0.0

                            if poids_a_sortir > stock_dispo:
                                st.error(f"❌ Impossible d'expédier ! Stock insuffisant dans {magasin_depart} (Disponible : {stock_dispo:,.0f} kg).")
                            else:
                                date_sortie = datetime.now().strftime("%Y-%m-%d %H:%M")
                                num_bl_genere = f"BL-{datetime.now().strftime('%Y%m%d')}-{id_vente_sel:04d}"
                                
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        INSERT INTO stock (date, type, quantite_kg, origine, magasin_destination, commentaire) 
                                        VALUES (%s, 'Sortie', %s, 'Expédition', %s, %s)
                                    """, (date_sortie, poids_a_sortir, magasin_depart, f"Livraison Vente N°{id_vente_sel} (Camion: {camion_bl})"))
                                    
                                    cur.execute("""
                                        INSERT INTO bons_livraison (id_vente, date_creation, quantite_a_livrer, statut)
                                        VALUES (%s, %s, %s, %s)
                                    """, (id_vente_sel, date_sortie, poids_a_sortir, 'Validé'))
                                    
                                    cur.execute("UPDATE ventes SET statut_livraison = 'Livré' WHERE id = %s", (id_vente_sel,))
                                    conn.commit()

                                data_bl = {
                                    "num_bl": num_bl_genere,
                                    "date": date_sortie,
                                    "magasin_depart": magasin_depart,
                                    "destination": destination,
                                    "poids_net": poids_a_sortir,
                                    "sacs": sacs_sortis,
                                    "taux_humidite": taux_humidite,
                                    "taux_moisissure": taux_moisissure,
                                    "nature": nature_produit,
                                    "camion": camion_bl,
                                    "chauffeur": chauffeur_bl
                                }

                                pdf_path = generer_bordereau_livraison_pdf(data_bl)
                                with open(pdf_path, "rb") as f:
                                    pdf_bytes = f.read()

                                if 'get_stock_actuel' in globals():
                                    get_stock_actuel.clear()

                                st.session_state["data_bl"] = data_bl
                                st.session_state["pdf_bytes_bl"] = pdf_bytes
                                st.session_state["bl_pret"] = True
                                st.toast("✅ Sortie validée avec succès !", icon="🚀")
                                st.rerun()

    # =====================================================================
    # ---- ONGLET 3 : ÉTAT DES STOCKS
    # =====================================================================
    with tab3:
        st.subheader("📊 Inventaire détaillé par lot")

        query_magasins = """
            SELECT 
                m.id, 
                m.nom, 
                m.emplacement, 
                m.capacite_kg, 
                m.responsable,
                COALESCE((
                    SELECT SUM(quantite_kg) FROM stock 
                    WHERE magasin_destination = m.nom AND type = 'Entrée'
                ), 0) 
                - COALESCE((
                    SELECT SUM(quantite_kg) FROM stock 
                    WHERE magasin_destination = m.nom AND type = 'Sortie'
                ), 0) AS stock_actuel
            FROM magasins m
            ORDER BY m.id DESC
        """
        df_magasins = get_dataframe_from_query(query_magasins)
        
        if not df_magasins.empty:
            cols_jauges = st.columns(min(len(df_magasins), 4))
            for idx, row in df_magasins.iterrows():
                with cols_jauges[idx % 4]:
                    cap_kg = float(row['capacite_kg']) if pd.notnull(row['capacite_kg']) else 0.0
                    stock_actuel = float(row['stock_actuel']) if pd.notnull(row['stock_actuel']) else 0.0
                    if cap_kg > 0:
                        percent = max(0.0, min(stock_actuel / cap_kg, 1.0))
                        color = "🔴 Rempli" if percent > 0.9 else "🟡 Modéré" if percent > 0.6 else "🟢 Espace disponible"
                        st.metric(f"🏢 {row['nom']}", f"{stock_actuel:,.0f} kg")
                        st.progress(percent)
                        st.caption(f"{color} ({cap_kg:,.0f} kg max)")
                    else:
                        st.metric(f"🏢 {row['nom']}", f"{stock_actuel:,.0f} kg")
                        st.caption("Capacité non définie")
            st.divider()

        st.markdown("#### 📋 Détail des réceptions par lot")

        query_detail = """
        SELECT
            a.id AS id_achat,
            a.numero_de_lot AS "Lot",
            TO_CHAR(a.date, 'YYYY-MM-DD HH24:MI') AS "Date_Reception",
            f.nom AS "Fournisseur",
            s.numero_camion AS "Camion",
            s.provenance AS "Provenance",
            a.nombre_de_sacs AS "Sacs",
            a.poids_brut AS "Poids_Brut",
            a.poids_net AS "Poids_Net",
            s.refaction AS "Refaction",
            a.poids_net_paye AS "Poids_Net_Payable",
            m.nom AS "Magasin",
            a.statut AS "Statut_Facturation",
            aq.taux_humidite AS "Humidite",
            aq.statut_qualite AS "Qualite",
            s.quantite_kg AS "Quantite_Stock"
        FROM stock s
        JOIN achats a ON s.id_achat = a.id
        JOIN fournisseurs f ON a.id_fournisseur = f.id
        LEFT JOIN analyses_qualite aq ON a.id = aq.id_achat
        LEFT JOIN magasins m ON s.magasin_destination = m.nom
        WHERE s.type = 'Entrée'
        AND s.quantite_kg > 0
        ORDER BY a.date DESC
        """
        df_detail = get_dataframe_from_query(query_detail)

        if df_detail.empty:
            st.info("Aucun lot en stock pour le moment.")
        else:
            col_f1, col_f2, col_f3 = st.columns(3)
            magasins_list = df_detail['Magasin'].dropna().unique().tolist()
            magasin_filter = col_f1.selectbox("🏢 Filtrer par magasin", ["Tous"] + magasins_list, key="magasin_inventaire_filter")
            fournisseurs_list = df_detail['Fournisseur'].unique().tolist()
            fourn_filter = col_f2.selectbox("🏢 Filtrer par fournisseur", ["Tous"] + fournisseurs_list, key="magasin_inventaire_fournisseur")
            search = col_f3.text_input("🔍 Recherche (lot, camion, provenance)", "", key="magasin_inventaire_search")

            df_filtre = df_detail.copy()
            if magasin_filter != "Tous":
                df_filtre = df_filtre[df_filtre['Magasin'] == magasin_filter]
            if fourn_filter != "Tous":
                df_filtre = df_filtre[df_filtre['Fournisseur'] == fourn_filter]
            if search:
                mask = (
                    df_filtre['Lot'].str.contains(search, case=False, na=False) |
                    df_filtre['Camion'].str.contains(search, case=False, na=False) |
                    df_filtre['Provenance'].str.contains(search, case=False, na=False)
                )
                df_filtre = df_filtre[mask]

            if df_filtre.empty:
                st.warning("Aucun résultat pour ces critères.")
            else:
                total_kgs = df_filtre['Poids_Net_Payable'].sum()
                total_sacs = df_filtre['Sacs'].sum()
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("📦 Lots en stock", len(df_filtre))
                col_m2.metric("⚖️ Poids total payable", f"{total_kgs:,.2f} kg")
                col_m3.metric("🛍️ Nombre total de sacs", f"{total_sacs:,.0f}")

                st.divider()

                st.dataframe(
                    df_filtre,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "id_achat": st.column_config.NumberColumn("ID", width="small"),
                        "Lot": st.column_config.TextColumn("Lot"),
                        "Date_Reception": st.column_config.DatetimeColumn("Date réception", format="DD/MM/YYYY HH:mm"),
                        "Fournisseur": st.column_config.TextColumn("Fournisseur"),
                        "Camion": st.column_config.TextColumn("Camion"),
                        "Provenance": st.column_config.TextColumn("Provenance"),
                        "Sacs": st.column_config.NumberColumn("Sacs", format="%d"),
                        "Poids_Brut": st.column_config.NumberColumn("Poids brut (kg)", format="%.2f"),
                        "Poids_Net": st.column_config.NumberColumn("Poids net (kg)", format="%.2f"),
                        "Refaction": st.column_config.NumberColumn("Réfaction (kg)", format="%.2f"),
                        "Poids_Net_Payable": st.column_config.NumberColumn("Net payable (kg)", format="%.2f"),
                        "Magasin": st.column_config.TextColumn("Magasin"),
                        "Statut": st.column_config.TextColumn("Statut facturation"),
                        "Humidite": st.column_config.NumberColumn("Humidité (%)", format="%.1f"),
                        "Qualite": st.column_config.TextColumn("Qualité"),
                    }
                )

                col_exp1, col_exp2 = st.columns(2)
                with col_exp1:
                    st.download_button(
                        "📥 Exporter CSV",
                        df_filtre.to_csv(index=False).encode('utf-8'),
                        "stock_detaille.csv",
                        "text/csv",
                        use_container_width=True
                    )
                with col_exp2:
                    try:
                        st.download_button(
                            "📥 Exporter Excel",
                            convertir_df_excel(df_filtre),
                            "stock_detaille.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True
                        )
                    except NameError:
                        pass

    # =====================================================================
    # ---- ONGLET 4 : PARAMÈTRES
    # =====================================================================
    with tab4:
        st.subheader("⚙️ Configuration des Sites")
        
        with st.expander("➕ CRÉER UNE NOUVELLE ZONE DE STOCKAGE", expanded=False):
            with st.form("form_magasin", clear_on_submit=True):
                nom_magasin = st.text_input("Nom de l'Entrepôt / Magasin *")
                emplacement = st.text_input("Ville ou Zone (ex: Zone Portuaire)")
                capacite = st.number_input("Capacité maximale (en kg)", min_value=0.0, step=1000.0)
                responsable = st.text_input("Gestionnaire attitré")
                
                submitted = st.form_submit_button("💾 Enregistrer le Magasin", use_container_width=True)
                if submitted:
                    if not nom_magasin:
                        st.error("❌ Le nom du magasin est obligatoire.")
                    else:
                        date_now = datetime.now().strftime("%Y-%m-%d %H:%M")
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO magasins (nom, emplacement, capacite_kg, responsable, date_ajout)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (nom_magasin, emplacement, capacite, responsable, date_now))
                            conn.commit()
                        st.toast(f"✅ L'entrepôt '{nom_magasin}' est opérationnel !", icon="🏗️")
                        st.rerun()
                        
        with st.expander("📝 ADMINISTRER LES SITES EXISTANTS", expanded=False):
            magasins_liste_mod = fetch_all("SELECT id, nom FROM magasins")
            
            if not magasins_liste_mod:
                st.info("Aucune donnée disponible.")
            else:
                dict_m = {f"{m[1]} (Réf: {m[0]})": m[0] for m in magasins_liste_mod}
                choix_m = st.selectbox("Sélectionner le site à modifier", list(dict_m.keys()))
                id_selectionne = dict_m[choix_m]
                
                magasin_data = fetch_one("SELECT nom, emplacement, capacite_kg, responsable FROM magasins WHERE id = %s", (id_selectionne,))
                
                if magasin_data:
                    val_nom = magasin_data[0] if magasin_data[0] is not None else ""
                    val_empl = magasin_data[1] if magasin_data[1] is not None else ""
                    val_cap = float(magasin_data[2]) if magasin_data[2] is not None else 0.0
                    val_resp = magasin_data[3] if magasin_data[3] is not None else ""

                    with st.form("form_edit_magasin"):
                        new_nom = st.text_input("Nom", value=val_nom)
                        new_empl = st.text_input("Emplacement", value=val_empl)
                        new_cap = st.number_input("Capacité maximale (kg)", min_value=0.0, step=1000.0, value=val_cap)
                        new_resp = st.text_input("Responsable", value=val_resp)
                        
                        col_btn1, col_btn2 = st.columns(2)
                        btn_modifier = col_btn1.form_submit_button("🔄 Mettre à jour", use_container_width=True)
                        btn_supprimer = col_btn2.form_submit_button("🗑️ Supprimer le site", use_container_width=True)
                        
                        if btn_modifier:
                            if not new_nom:
                                st.error("❌ Le nom ne peut pas être vide.")
                            else:
                                with conn.cursor() as cur:
                                    cur.execute("""
                                        UPDATE magasins SET nom = %s, emplacement = %s, capacite_kg = %s, responsable = %s WHERE id = %s
                                    """, (new_nom, new_empl, new_cap, new_resp, id_selectionne))
                                    conn.commit()
                                st.toast("✅ Mise à jour effectuée.", icon="👍")
                                st.rerun()
                                
                        if btn_supprimer:
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM magasins WHERE id = %s", (id_selectionne,))
                                conn.commit()
                            st.toast("✅ Site supprimé définitivement.", icon="🗑️")
                            st.rerun()

    # =====================================================================
    # ---- ONGLET 5 : UNITÉ D'ANALYSE
    # =====================================================================
    with tab5:
        st.subheader("🧪 Unité d'Analyse Qualité Cacao")

        if "analyse_pdf_bytes" not in st.session_state:
            st.session_state.analyse_pdf_bytes = None
            st.session_state.analyse_pdf_name = None
            st.session_state.analyse_last_ref = None

        if st.session_state.analyse_pdf_bytes:
            with st.container(border=True):
                st.success(
                    f"✅ Dernier bulletin généré pour la référence "
                    f"**{st.session_state.analyse_last_ref or 'N/A'}** — prêt à imprimer."
                )
                st.download_button(
                    label="📥 Télécharger le Bulletin d'Analyse (PDF)",
                    data=st.session_state.analyse_pdf_bytes,
                    file_name=st.session_state.analyse_pdf_name or "Bulletin_Analyse.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    type="primary",
                    key="dl_analyse_pdf_top",
                )
                if st.button("🗑️ Effacer l'aperçu PDF", key="clear_analyse_pdf"):
                    st.session_state.analyse_pdf_bytes = None
                    st.session_state.analyse_pdf_name = None
                    st.session_state.analyse_last_ref = None
                    st.rerun()

        st.divider()

        def get_lots_analysables(type_analyse):
            if type_analyse == "TV":
                return fetch_all("""
                    SELECT 
                        a.id,
                        a.numero_de_lot,
                        a.numero_contrat,
                        f.nom AS fournisseur,
                        COALESCE(a.poids_brut::numeric, 0) AS poids_brut,
                        COALESCE(a.poids_net::numeric, 0) AS poids_net,
                        COALESCE(a.poids_net_paye, 0) AS poids_net_paye,
                        COALESCE(a.nombre_de_sacs, 0) AS nb_sacs,
                        a.date,
                        a.numero_br
                    FROM achats a
                    JOIN fournisseurs f ON a.id_fournisseur = f.id
                    WHERE a.statut = 'En attente de facturation'
                    AND NOT EXISTS (
                        SELECT 1
                        FROM analyses_qualite aq
                        WHERE aq.id_achat = a.id
                            AND aq.type_analyse = 'TV'
                            AND aq.statut_qualite IS NOT NULL
                    )
                    ORDER BY a.date DESC
                """)
            elif type_analyse == "Export":
                return fetch_all("""
                    SELECT 
                        v.id AS id_vente,
                        v.client_nom AS client,
                        v.quantite_kg AS quantite_vendue,
                        v.date_vente,
                        v.total,
                        v.devise,
                        v.incoterm,
                        v.port_embarquement,
                        v.port_dechargement,
                        v.termes_paiement,
                        m.nom AS magasin,
                        COALESCE((
                            SELECT fichier_pdf FROM documents_generes
                            WHERE type_doc = 'facture_vente'
                            AND reference = 'INV-' || LPAD(v.id::text, 4, '0')
                            AND statut = 'VALIDE'
                        ), NULL) AS facture_validee,
                        v.id_magasin
                    FROM ventes v
                    JOIN magasins m ON v.id_magasin = m.id
                    WHERE v.statut_livraison = 'En attente d''expédition'
                    AND NOT EXISTS (
                        SELECT 1 FROM analyses_qualite aq
                        WHERE aq.id_vente = v.id AND aq.type_analyse = 'Export'
                        AND aq.statut_qualite IS NOT NULL
                    )
                    ORDER BY v.id DESC
                """)
            return []

        sub_new, sub_hist = st.tabs(["🆕 Nouvelle Analyse", "📚 Historique des analyses"])

        with sub_new:
            type_bulletin = st.radio(
                "Type de bulletin",
                ["Tout Venant (TV)", "Export"],
                horizontal=True,
                key="type_bulletin_analyse",
                help="TV = contrôle réception magasin. Export = bulletin complet pour client / douane.",
            )
            is_export = (type_bulletin == "Export")

            lots_a_analyser = get_lots_analysables("Export" if is_export else "TV")

            if not lots_a_analyser:
                st.success("✅ Tous les éléments éligibles ont déjà été analysés.")
            else:
                if is_export:
                    dict_lots = {}

                    for v in lots_a_analyser:
                        id_vente = v[0]
                        client = v[1]
                        qte = float(v[2] or 0)
                        date_vente = v[3]

                        # Conversion sécurisée de la date
                        if date_vente is None:
                            date_vente_str = "N/A"
                        elif hasattr(date_vente, "strftime"):
                            date_vente_str = date_vente.strftime("%Y-%m-%d")
                        else:
                            date_vente_str = str(date_vente)[:10]

                        total = float(v[4] or 0)
                        devise = v[5]
                        incoterm = v[6]
                        port_emb = v[7]
                        port_decharg = v[8]
                        termes = v[9]
                        magasin = v[10]
                        facture_validee = v[11]
                        id_magasin = v[12]

                        # Une vente sans facture validée n'est pas analysable
                        if facture_validee is None:
                            continue

                        # IMPORTANT : utiliser date_vente_str et non date_vente[:10]
                        label = (
                            f"Vente N°{id_vente:04d} — {client} | "
                            f"{qte:,.0f} kg | {date_vente_str}"
                        )

                        dict_lots[label] = {
                            "id_vente": id_vente,
                            "client": client,
                            "quantite_vendue": qte,
                            "date_vente": date_vente,
                            "date_vente_str": date_vente_str,
                            "total": total,
                            "devise": devise,
                            "incoterm": incoterm,
                            "port_embarquement": port_emb,
                            "port_dechargement": port_decharg,
                            "termes_paiement": termes,
                            "magasin": magasin,
                            "id_magasin": id_magasin,
                            "facture_validee": facture_validee,
                        }
                else:
                    dict_lots = {}
                    for lot in lots_a_analyser:
                        label = f"Lot {lot[1]} — {lot[3]} | Net: {float(lot[5] or 0):,.0f} kg | Contrat: {lot[2] or 'N/A'}"
                        dict_lots[label] = {
                            "id_achat": lot[0],
                            "num_lot": lot[1],
                            "num_contrat": lot[2],
                            "fournisseur": lot[3],
                            "poids_brut": float(lot[4] or 0),
                            "poids_net": float(lot[5] or 0),
                            "poids_net_paye": float(lot[6] or 0),
                            "nb_sacs": int(lot[7] or 0),
                            "date_reception": lot[8],
                            "numero_br": lot[9] if len(lot) > 9 else None,
                        }

                if not dict_lots:
                    st.warning("Aucun élément éligible après filtrage.")
                else:
                    selection = st.selectbox(
                        "📦 Sélectionnez l'élément à analyser",
                        list(dict_lots.keys()),
                        key="sel_lot_analyse",
                    )
                    infos = dict_lots[selection]

                    if is_export:
                        id_reference = infos["id_vente"]
                        client_fournisseur = infos["client"]
                        reference_contrat = f"INV-{id_reference:04d}"
                        numero_bulletin = f"BA-EXP-{id_reference:04d}"
                        poids_net_base = infos["quantite_vendue"]
                        poids_brut = poids_net_base
                        infos_vente = infos
                    else:
                        id_reference = infos["id_achat"]
                        client_fournisseur = infos["fournisseur"]
                        reference_contrat = infos["num_contrat"]
                        numero_bulletin = infos['numero_br'] if infos.get('numero_br') else f"BR-{infos['num_lot']}"
                        poids_net_base = infos["poids_net"] if infos["poids_net"] > 0 else infos["poids_brut"]
                        poids_brut = infos["poids_brut"]

                    if is_export:
                        date_aff = infos.get('date_vente_str', str(infos['date_vente'])[:10])
                        st.markdown(
                            f"**Vente N°{infos['id_vente']:04d}** &nbsp;|&nbsp; "
                            f"**Client :** {infos['client']} &nbsp;|&nbsp; "
                            f"**Quantité :** {poids_net_base:,.2f} kg &nbsp;|&nbsp; "
                            f"**Date :** {date_aff}"
                        )
                    else:
                        st.markdown(
                            f"**Lot :** `{infos['num_lot']}` &nbsp;|&nbsp; "
                            f"**Fournisseur :** {infos['fournisseur']} &nbsp;|&nbsp; "
                            f"**Contrat :** {infos['num_contrat'] or 'N/A'} &nbsp;|&nbsp; "
                            f"**Poids Net réception :** {poids_net_base:,.2f} kg"
                        )

                    st.markdown("---")
                    st.markdown("### 🔬 Saisie de l'échantillon (calculs en direct)")

                    poids_total = st.number_input(
                        "Poids Total Échantillon (g)",
                        min_value=1.0,
                        value=2000.0,
                        step=10.0,
                        key="an_poids_total",
                    )

                    st.markdown("**1. Tamisage, Fèves Plates & Corps Étrangers**")
                    c1, c2, c3 = st.columns(3)
                    with c1:
                        p_debris = st.number_input("Débris Tamisage (g)", min_value=0.0, value=0.0, step=0.01, key="an_debris")
                        t_debris = (p_debris / poids_total * 100) if poids_total > 0 else 0.0
                        st.caption(f"Taux : **{t_debris:.2f} %**")
                    with c2:
                        p_plates = st.number_input("Fèves Plates (g)", min_value=0.0, value=0.0, step=0.01, key="an_plates")
                        t_plates = (p_plates / poids_total * 100) if poids_total > 0 else 0.0
                        st.caption(f"Taux : **{t_plates:.2f} %**")
                    with c3:
                        p_etrangers = st.number_input("Corps Étrangers (g)", min_value=0.0, value=0.0, step=0.01, key="an_etrangers")
                        t_etrangers = (p_etrangers / poids_total * 100) if poids_total > 0 else 0.0
                        st.caption(f"Taux : **{t_etrangers:.2f} %**")

                    st.markdown("**2. Matière Dérivée du Cacao (MDC)**")
                    mc1, mc2, mc3 = st.columns(3)
                    with mc1:
                        p_crabots = st.number_input("Crabots (g)", min_value=0.0, value=0.0, step=0.01, key="an_crabots")
                        t_crabots = (p_crabots / poids_total * 100) if poids_total > 0 else 0.0
                        st.caption(f"Taux : **{t_crabots:.2f} %**")
                    with mc2:
                        p_brisees = st.number_input("Fèves Brisées (g)", min_value=0.0, value=0.0, step=0.01, key="an_brisees")
                        t_brisees = (p_brisees / poids_total * 100) if poids_total > 0 else 0.0
                        st.caption(f"Taux : **{t_brisees:.2f} %**")
                    with mc3:
                        p_frag = st.number_input("Fragments / Coques (g)", min_value=0.0, value=0.0, step=0.01, key="an_frag")
                        t_frag = (p_frag / poids_total * 100) if poids_total > 0 else 0.0
                        st.caption(f"Taux : **{t_frag:.2f} %**")

                    st_mdc_poids = p_crabots + p_brisees + p_frag
                    st_mdc_taux = (st_mdc_poids / poids_total * 100) if poids_total > 0 else 0.0
                    st.info(f"**Sous-Total MDC :** {st_mdc_poids:.2f} g  |  **{st_mdc_taux:.2f} %**")

                    st.markdown("**3. Humidité & Épreuve à la Coupe**")
                    humidite = st.number_input(
                        "Taux d'Humidité (%)",
                        min_value=0.0, max_value=100.0, value=8.0, step=0.1,
                        key="an_humidite"
                    )

                    st.markdown("**Épreuve à la coupe (3 x 100 fèves) — Saisir les décomptes pour chaque coupe**")
                    defauts = [
                        ("Moisissures", "moisies"),
                        ("Ardoises", "ardoisees"),
                        ("Mitées", "mitees"),
                        ("Germées", "germees"),
                        ("Violettes", "violettes"),
                        ("White spots", "white_spots"),
                    ]
                    valeurs_c = {}
                    moyennes = {}
                    for label, key in defauts:
                        cols = st.columns(3)
                        with cols[0]:
                            c1 = st.number_input(f"{label} C1", min_value=0, max_value=100, value=0, step=1, key=f"an_{key}_c1")
                        with cols[1]:
                            c2 = st.number_input(f"{label} C2", min_value=0, max_value=100, value=0, step=1, key=f"an_{key}_c2")
                        with cols[2]:
                            c3 = st.number_input(f"{label} C3", min_value=0, max_value=100, value=0, step=1, key=f"an_{key}_c3")
                        moyenne = (c1 + c2 + c3) / 3
                        st.caption(f"Moyenne : {moyenne:.1f} %")
                        valeurs_c[f"{key}_c1"] = c1
                        valeurs_c[f"{key}_c2"] = c2
                        valeurs_c[f"{key}_c3"] = c3
                        moyennes[key] = moyenne

                    pct_moisies = moyennes['moisies']
                    pct_ardoisees = moyennes['ardoisees']
                    pct_mitees = moyennes['mitees']
                    pct_germees = moyennes['germees']
                    pct_violettes = moyennes['violettes']
                    pct_white_spots = moyennes['white_spots']

                    st.markdown("**Grainage**")
                    feves_600g = st.number_input(
                        "Nombre de fèves dans 600 g (pour le grainage)",
                        min_value=0, value=0, step=1, key="an_feves_600"
                    )
                    feves_100g = (feves_600g / 6.0) if feves_600g else 0.0
                    st.caption(f"≈ **{feves_100g:.1f}** fèves / 100 g")
                    if feves_100g > 120:
                        st.error("⚠️ GRAINAGE > 120 fèves/100g → REJET AUTOMATIQUE")

                    if is_export:
                        st.markdown("**Compléments Export (organoleptique)**")
                        col_odeur, col_rem = st.columns(2)
                        with col_odeur:
                            contamination_odeur = st.selectbox(
                                "Odeur / Contamination",
                                ["Conforme", "Typique", "Moisi", "Fumé/Hammy", "Autre"],
                                key="an_odeur"
                            )
                        with col_rem:
                            remarques = st.text_input("Remarques", key="an_remarques")
                    else:
                        contamination_odeur = "Conforme"
                        remarques = ""

                    analyste = st.text_input("Nom de l'analyste *", key="an_analyste")

                    deductions = calculer_refractions_avec_coeff(
                        poids_net=poids_net_base,
                        humidite=humidite,
                        taux_debris=t_debris,
                        taux_etrangers=t_etrangers,
                        taux_plates=t_plates,
                        taux_mdc=st_mdc_taux,
                    )
                    ref_humidite = deductions['réfactions_détaillées'].get('humidite', 0.0)
                    ref_debris = deductions['réfactions_détaillées'].get('debris', 0.0)
                    ref_etrangers = deductions['réfactions_détaillées'].get('etrangers', 0.0)
                    ref_plates = deductions['réfactions_détaillées'].get('plates', 0.0)
                    ref_mdc = deductions['réfactions_détaillées'].get('mdc', 0.0)
                    total_ref = deductions['total_réfaction']
                    poids_net_paye = deductions['poids_net_payable']

                    if (humidite > 12.0 or pct_moisies > 12.0 or pct_ardoisees > 12.0 or
                        t_debris > 5.0 or t_etrangers > 5.0 or t_plates > 10.0 or
                        (pct_mitees + pct_germees + t_crabots + t_brisees + t_frag) > 10.0):
                        statut_qualite = "REJETE"
                    elif (humidite > 8.0 or t_debris > 1.5 or t_etrangers > 0.75 or
                        (t_crabots + t_brisees + t_frag) > 3.0):
                        statut_qualite = "REFACTURE"
                    else:
                        statut_qualite = "CONFORME"

                    decision = determiner_statut_qualite(
                        humidite=humidite,
                        taux_debris=t_debris,
                        taux_etrangers=t_etrangers,
                        taux_mdc=st_mdc_taux,
                        moisies=pct_moisies,
                        ardoisees=pct_ardoisees,
                        grainage=feves_100g,
                        contamination=contamination_odeur,
                    )
                    statut_qualite = decision["statut"]

                    st.markdown("---")
                    st.subheader("⚖️ Résultats & Réfactions (temps réel)")
                    col_r1, col_r2, col_r3 = st.columns(3)
                    col_r1.metric("Poids Net Base", f"{poids_net_base:,.2f} kg")
                    col_r2.metric("Total Réfactions", f"- {total_ref:,.2f} kg")
                    col_r3.metric("POIDS NET PAYABLE", f"{poids_net_paye:,.2f} kg", delta=statut_qualite)

                    with st.expander("📋 Détail des réfactions appliquées"):
                        st.write("**Déductions :**")
                        for label, val in deductions['réfactions_détaillées'].items():
                            if val > 0:
                                st.write(f"- {label} : {val:,.2f} kg")
                        if total_ref == 0:
                            st.write("Aucune réfaction appliquée.")
                        st.write(f"**Total :** {total_ref:,.2f} kg")
                        st.write(f"**Poids net payable :** {poids_net_paye:,.2f} kg")

                    st.markdown("---")
                    if st.button(
                        "💾 Valider l'Analyse et Générer le Bulletin",
                        type="primary",
                        use_container_width=True,
                        key="btn_valider_analyse",
                    ):
                        if not analyste or not analyste.strip():
                            st.error("❌ Le nom de l'analyste est obligatoire.")
                        elif poids_total <= 0:
                            st.error("❌ Poids d'échantillon invalide.")
                        else:
                            try:
                                with conn.cursor() as cur:
                                    if is_export:
                                        data_analyse = {
                                            "id_vente": infos["id_vente"],
                                            "id_achat": None,
                                            "numero_br": numero_bulletin,
                                            "contrat_no": f"INV-{infos['id_vente']:04d}",
                                            "origine_ex": infos["client"],
                                            "vendeur": infos["client"],
                                            "poids_total_echantillon": poids_total,
                                            "poids_debris_tamisage": p_debris,
                                            "taux_debris_tamisage": t_debris,
                                            "poids_feves_plates": p_plates,
                                            "taux_feves_plates": t_plates,
                                            "poids_corps_etrangers": p_etrangers,
                                            "taux_corps_etrangers": t_etrangers,
                                            "poids_crabots": p_crabots,
                                            "taux_crabots": t_crabots,
                                            "poids_feves_brisees": p_brisees,
                                            "taux_feves_brisees": t_brisees,
                                            "poids_fragments_coques": p_frag,
                                            "taux_fragments_coques": t_frag,
                                            "poids_sous_total_mdc": st_mdc_poids,
                                            "taux_sous_total_mdc": st_mdc_taux,
                                            "taux_humidite": humidite,
                                            "feves_moisies_pct": pct_moisies,
                                            "feves_ardoisees_pct": pct_ardoisees,
                                            "feves_mitees_pct": pct_mitees,
                                            "feves_germees_pct": pct_germees,
                                            "feves_violettes_pct": pct_violettes,
                                            "white_spots_pct": pct_white_spots,
                                            "contamination_odeur": contamination_odeur,
                                            "remarques": remarques,
                                            "analyste": analyste.strip(),
                                            "statut_qualite": statut_qualite,
                                            "feves_moisies_c1": valeurs_c['moisies_c1'],
                                            "feves_moisies_c2": valeurs_c['moisies_c2'],
                                            "feves_moisies_c3": valeurs_c['moisies_c3'],
                                            "feves_ardoisees_c1": valeurs_c['ardoisees_c1'],
                                            "feves_ardoisees_c2": valeurs_c['ardoisees_c2'],
                                            "feves_ardoisees_c3": valeurs_c['ardoisees_c3'],
                                            "feves_mitees_c1": valeurs_c['mitees_c1'],
                                            "feves_mitees_c2": valeurs_c['mitees_c2'],
                                            "feves_mitees_c3": valeurs_c['mitees_c3'],
                                            "feves_germees_c1": valeurs_c['germees_c1'],
                                            "feves_germees_c2": valeurs_c['germees_c2'],
                                            "feves_germees_c3": valeurs_c['germees_c3'],
                                            "feves_violettes_c1": valeurs_c['violettes_c1'],
                                            "feves_violettes_c2": valeurs_c['violettes_c2'],
                                            "feves_violettes_c3": valeurs_c['violettes_c3'],
                                            "white_spots_c1": valeurs_c['white_spots_c1'],
                                            "white_spots_c2": valeurs_c['white_spots_c2'],
                                            "white_spots_c3": valeurs_c['white_spots_c3'],
                                            "feves_dans_600g": feves_600g,
                                            "feves_pour_100g": feves_100g,
                                            "type_analyse": 'Export'
                                        }
                                        insert_dict(cur, "analyses_qualite", data_analyse)
                                    else:
                                        data_analyse = {
                                            "id_achat": infos["id_achat"],
                                            "id_vente": None,
                                            "numero_br": numero_bulletin,
                                            "contrat_no": infos["num_contrat"],
                                            "origine_ex": infos["fournisseur"],
                                            "vendeur": infos["fournisseur"],
                                            "poids_total_echantillon": poids_total,
                                            "poids_debris_tamisage": p_debris,
                                            "taux_debris_tamisage": t_debris,
                                            "poids_feves_plates": p_plates,
                                            "taux_feves_plates": t_plates,
                                            "poids_corps_etrangers": p_etrangers,
                                            "taux_corps_etrangers": t_etrangers,
                                            "poids_crabots": p_crabots,
                                            "taux_crabots": t_crabots,
                                            "poids_feves_brisees": p_brisees,
                                            "taux_feves_brisees": t_brisees,
                                            "poids_fragments_coques": p_frag,
                                            "taux_fragments_coques": t_frag,
                                            "poids_sous_total_mdc": st_mdc_poids,
                                            "taux_sous_total_mdc": st_mdc_taux,
                                            "taux_humidite": humidite,
                                            "feves_moisies_pct": pct_moisies,
                                            "feves_ardoisees_pct": pct_ardoisees,
                                            "feves_mitees_pct": pct_mitees,
                                            "feves_germees_pct": pct_germees,
                                            "feves_violettes_pct": pct_violettes,
                                            "white_spots_pct": pct_white_spots,
                                            "contamination_odeur": contamination_odeur,
                                            "remarques": remarques,
                                            "analyste": analyste.strip(),
                                            "statut_qualite": statut_qualite,
                                            "feves_moisies_c1": valeurs_c['moisies_c1'],
                                            "feves_moisies_c2": valeurs_c['moisies_c2'],
                                            "feves_moisies_c3": valeurs_c['moisies_c3'],
                                            "feves_ardoisees_c1": valeurs_c['ardoisees_c1'],
                                            "feves_ardoisees_c2": valeurs_c['ardoisees_c2'],
                                            "feves_ardoisees_c3": valeurs_c['ardoisees_c3'],
                                            "feves_mitees_c1": valeurs_c['mitees_c1'],
                                            "feves_mitees_c2": valeurs_c['mitees_c2'],
                                            "feves_mitees_c3": valeurs_c['mitees_c3'],
                                            "feves_germees_c1": valeurs_c['germees_c1'],
                                            "feves_germees_c2": valeurs_c['germees_c2'],
                                            "feves_germees_c3": valeurs_c['germees_c3'],
                                            "feves_violettes_c1": valeurs_c['violettes_c1'],
                                            "feves_violettes_c2": valeurs_c['violettes_c2'],
                                            "feves_violettes_c3": valeurs_c['violettes_c3'],
                                            "white_spots_c1": valeurs_c['white_spots_c1'],
                                            "white_spots_c2": valeurs_c['white_spots_c2'],
                                            "white_spots_c3": valeurs_c['white_spots_c3'],
                                            "feves_dans_600g": feves_600g,
                                            "feves_pour_100g": feves_100g,
                                            "type_analyse": 'TV'
                                        }
                                        insert_dict(cur, "analyses_qualite", data_analyse)
                                        # Mise à jour de l'achat et du stock
                                        cur.execute("""
                                            UPDATE achats
                                            SET poids_net_paye = %s,
                                                quantite_kg = %s
                                            WHERE id = %s
                                        """, (poids_net_paye, poids_net_paye, infos["id_achat"]))
                                        cur.execute("""
                                            UPDATE stock
                                            SET refaction = %s
                                            WHERE id_achat = %s
                                        """, (total_ref, infos["id_achat"]))

                                    conn.commit()

                                nom_fichier = f"Bulletin_{'Export' if is_export else 'TV'}_{numero_bulletin}.pdf"
                                try:
                                    data_analyse.update({
                                        "numero_lot": infos.get("num_lot") if not is_export else None,
                                        "poids_brut_receptionne": poids_brut,
                                        "poids_net_reception": poids_net_base,
                                        "fournisseur": infos["fournisseur"] if not is_export else infos.get("FRIENDS CAMEROON COMM0DITIES"),
                                        "poids_total": poids_total,
                                        "p_debris": p_debris, "t_debris": t_debris,
                                        "p_plates": p_plates, "t_plates": t_plates,
                                        "p_etrangers": p_etrangers, "t_etrangers": t_etrangers,
                                        "p_crabots": p_crabots, "t_crabots": t_crabots,
                                        "p_brisees": p_brisees, "t_brisees": t_brisees,
                                        "p_frag": p_frag, "t_frag": t_frag,
                                        "st_mdc_poids": st_mdc_poids, "st_mdc_taux": st_mdc_taux,
                                        "humidite": humidite,
                                        "pct_moisies": pct_moisies, "pct_ardoisees": pct_ardoisees,
                                        "pct_mitees": pct_mitees, "pct_germees": pct_germees,
                                        "pct_violettes": pct_violettes, "pct_white_spots": pct_white_spots,
                                        "type_bulletin": type_bulletin,
                                        "ref_humidite": ref_humidite, "ref_debris": ref_debris,
                                        "ref_etrangers": ref_etrangers, "ref_plates": ref_plates,
                                        "ref_mdc": ref_mdc, "total_ref": total_ref,
                                        "poids_net_paye": poids_net_paye,
                                        "coeff_applique": deductions.get('coeff_applique', 0.0),
                                        "plafond_applique": deductions.get('plafond_applique', 0),
                                        "plafond_pourcentage": deductions.get('plafond_pourcentage', 0.0),
                                    })


                                    resultat_pdf = generer_bulletin_analyse_cacao_pdf(data_analyse, nom_fichier)
                                    if isinstance(resultat_pdf, tuple):
                                        pdf_path, pdf_bytes = resultat_pdf
                                    else:
                                        pdf_path = resultat_pdf
                                        pdf_bytes = None
                                    if pdf_bytes is None or len(pdf_bytes) == 0:
                                        st.warning("⚠️ Analyse enregistrée, mais le PDF du bulletin n'a pas été généré correctement.")
                                        logging.error(f"PDF analyse vide pour {numero_bulletin}. Résultat fonction : {type(resultat_pdf)}")
                                    else:
                                        st.session_state.analyse_pdf_bytes = pdf_bytes
                                        st.session_state.analyse_pdf_name = nom_fichier
                                        st.session_state.analyse_last_ref = numero_bulletin
                                        st.success(f"📄 Bulletin {numero_bulletin} généré avec succès.")
                                        st.download_button(
                                            label="📥 Télécharger le Bulletin d'Analyse (PDF)",
                                            data=pdf_bytes,
                                            file_name=nom_fichier,
                                            mime="application/pdf",
                                            use_container_width=True,
                                            type="primary",
                                            key=f"download_bulletin_analyse_{numero_bulletin}"
                                        )
                                except Exception as pdf_error:
                                    logging.exception(f"Erreur génération PDF analyse {numero_bulletin}: {pdf_error}")
                                    st.warning(f"⚠️ Analyse enregistrée, mais impossible de générer le bulletin PDF : {pdf_error}")

                                log_action(f"Analyse {type_bulletin} validée — Réf {numero_bulletin} — Net payable {poids_net_paye:.2f} kg — {statut_qualite}")
                                st.toast(f"✅ Analyse enregistrée — Net payable {poids_net_paye:,.2f} kg", icon="🧪")

                            except Exception as e:
                                conn.rollback()
                                st.error(f"❌ Erreur lors de l'enregistrement : {e}")
                                logging.error(f"Erreur analyse qualité: {e}")

                    somme_defauts = (t_debris + t_plates + t_etrangers + t_crabots + t_brisees + t_frag +
                                    pct_moisies + pct_ardoisees + pct_mitees + pct_germees)
                    if somme_defauts > 100.0:
                        st.error(f"❌ La somme des taux de défauts ({somme_defauts:.2f}%) dépasse 100%. Veuillez vérifier vos saisies.")
                        st.stop()

        with sub_hist:
            st.markdown("#### 📚 Analyses déjà enregistrées")
            try:
                df_hist = get_dataframe_from_query("""
                    SELECT
                        aq.id,
                        aq.type_analyse AS "Type",
                        aq.numero_br AS "N° Bulletin",
                        COALESCE(ach.numero_de_lot, 'VENTE-' || LPAD(aq.id_vente::text, 4, '0')) AS "Lot/Vente",
                        aq.contrat_no AS "Contrat/Facture",
                        aq.origine_ex AS "Fournisseur/Client",
                        aq.taux_debris_tamisage AS "Débris %",
                        aq.taux_feves_plates AS "Plates %",
                        aq.taux_feves_brisees AS "Brisées %",
                        aq.taux_fragments_coques AS "Fragments %",
                        aq.taux_humidite AS "Humidité %",
                        aq.feves_moisies_pct AS "Moisies %",
                        aq.feves_ardoisees_pct AS "Ardoisées %",
                        aq.taux_corps_etrangers AS "Corps Étr. %",
                        aq.feves_mitees_pct AS "Mitées %",
                        aq.feves_germees_pct AS "Germées %",
                        aq.feves_violettes_pct AS "Violettes %",
                        aq.white_spots_pct AS "White Spots %",
                        aq.statut_qualite AS "Statut",
                        aq.analyste AS "Analyste",
                        aq.date_analyse AS "Date Analyse"
                    FROM analyses_qualite aq
                    LEFT JOIN achats ach ON aq.id_achat = ach.id
                    ORDER BY aq.id DESC
                    LIMIT 100
                """)
                if df_hist.empty:
                    st.info("Aucune analyse enregistrée pour le moment.")
                else:
                    st.dataframe(df_hist, use_container_width=True, hide_index=True)
            except Exception as e:
                st.error(f"Impossible de charger l'historique : {e}")
                
elif choix == "👑 Espace Direction":
    # --- En-tête premium ---
    st.markdown(
        """
        <div style="
            background: linear-gradient(135deg, #1e1b4b, #0f172a);
            border-radius: 16px;
            padding: 26px 30px;
            margin-bottom: 20px;
            border: 1px solid #312e81;
        ">
            <div style="font-size: 26px; font-weight: 800; color: #f8fafc;">
                👑 Espace Direction
            </div>
            <div style="font-size: 14px; color: #a5b4fc; margin-top: 2px;">
                Validation & cachets officiels
            </div>
            <div style="font-size: 13px; color: #94a3b8; margin-top: 8px;">
                Gestion centralisée des signatures électroniques et validation des actes officiels de l'entreprise.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    # --- RÉCUPÉRATION DYNAMIQUE DES RÔLES ENREGISTRÉS ---
    try:
        roles_existants = [row[0] for row in fetch_all("SELECT DISTINCT role_signataire FROM cachets_direction ORDER BY role_signataire")]
    except Exception as e:
        st.warning(f"Impossible de charger les rôles : {e}")
        roles_existants = []

    if not roles_existants:
        roles_existants = ["DG", "DGD", "DAF", "DRH", "DSI"]

    tab_valide, tab_archives, tab_cachets, tab_verif = st.tabs([
        "📋 Documents en Attente",
        "📂 Archives & Historique",
        "⚙️ Gestion des Cachets",
        "🔍 Vérification d'authenticité"
    ])

    # =========================================================================
    # ONGLET 1 : DOCUMENTS EN ATTENTE DE VALIDATION
    # =========================================================================
    with tab_valide:
        try:
            df_attente = get_dataframe_from_query("""
                SELECT id, type_doc, reference, montant, demandeur, description, date_creation 
                FROM documents_generes 
                WHERE statut = 'EN_ATTENTE' 
                ORDER BY date_creation DESC
            """)
        except Exception as e:
            st.error(f"❌ Erreur de lecture de la base de données : {e}")
            df_attente = pd.DataFrame()

        if df_attente.empty:
            st.markdown(
                """
                <div style="
                    background: linear-gradient(135deg, #052e16, #0f172a);
                    border: 1px solid #166534;
                    border-radius: 14px;
                    padding: 24px;
                    text-align: center;
                ">
                    <div style="font-size: 32px;">🎉</div>
                    <div style="font-size: 15px; color: #86efac; font-weight: 600; margin-top: 6px;">
                        Aucun document en attente
                    </div>
                    <div style="font-size: 13px; color: #94a3b8; margin-top: 2px;">
                        La corbeille de validation est parfaitement à jour.
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            col_kpi1, col_kpi2 = st.columns([1, 3])
            with col_kpi1:
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(135deg, #451a03, #0f172a);
                        border: 1px solid #92400e;
                        border-radius: 14px;
                        padding: 18px;
                        text-align: center;
                    ">
                        <div style="font-size: 28px; font-weight: 800; color: #fbbf24;">{len(df_attente)}</div>
                        <div style="font-size: 12px; color: #fcd34d; margin-top: 2px;">Document(s) à valider</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
            st.markdown("<br>", unsafe_allow_html=True)

            type_traduit_map = {
                'contrat': ('📜', 'Contrat'),
                'bon_paiement': ('📄', 'Bon de Paiement'),
                'bon_caisse': ('💵', 'Bon de Caisse (Acompte)'),
                'engagement_dette': ('📝', 'Engagement de Dette'),
                'facture_vente': ('🧾', 'Facture de Vente'),
                'reglement_dette': ('💳', 'Règlement de Dette')
            }

            for row in df_attente.to_dict('records'):
    # row est maintenant un dictionnaire
                doc_type = row['type_doc']
                doc_ref = row['reference']
                icone, libelle = type_traduit_map.get(row['type_doc'], ('📌', row['type_doc'].upper()))
                montant_affiche = f"{row['montant']:,.0f}" if pd.notnull(row['montant']) else "0"
                titre_carte = f"{icone} {libelle} — Réf: {row['reference']} · {montant_affiche} FCFA"

                with st.expander(titre_carte, expanded=False):
                    with st.container(border=True):

                        # -----------------------------------------------------
                        # 1. PRÉ-GÉNÉRATION DU PDF (Aperçu corrigé)
                        # -----------------------------------------------------
                        pdf_bytes = None
                        doc_type = row['type_doc']
                        doc_ref = row['reference']

                        try:
                            # CAS 1 : CONTRAT
                            if doc_type == 'contrat':
                                row_contrat = fetch_one("""
                                    SELECT 
                                        c.*,
                                        f.nom AS fournisseur,
                                        f.telephone, f.ville, f.adresse, 
                                        f.Rccm AS rccm, f.NUI AS nui, f.numero_de_compte AS compte
                                    FROM contrats c
                                    LEFT JOIN fournisseurs f ON c.id_fournisseur = f.id
                                    WHERE c.numero_contrat = %s
                                """, (doc_ref,))
                                if row_contrat:
                                    # Récupération des noms de colonnes pour construire le dict
                                    # On utilise get_dataframe_from_query pour obtenir les colonnes
                                    df_contrat = get_dataframe_from_query("""
                                        SELECT 
                                            c.*,
                                            f.nom AS fournisseur,
                                            f.telephone, f.ville, f.adresse, 
                                            f.Rccm AS rccm, f.NUI AS nui, f.numero_de_compte AS compte
                                        FROM contrats c
                                        LEFT JOIN fournisseurs f ON c.id_fournisseur = f.id
                                        WHERE c.numero_contrat = %s
                                    """, (doc_ref,))
                                    if not df_contrat.empty:
                                        data_contrat = df_contrat.iloc[0].to_dict()
                                        data_contrat["num"] = data_contrat.get("numero_contrat", doc_ref)
                                        data_contrat["qte"] = data_contrat.get("quantite_prevue", data_contrat.get("quantite", 0))
                                        data_contrat["pu"] = data_contrat.get("prix_unitaire", 0)
                                        data_contrat["delai"] = data_contrat.get("delai_livraison", "N/A")
                                        data_contrat["lieu"] = data_contrat.get("lieu_livraison", "N/A")
                                        data_contrat["date"] = datetime.now().strftime("%d/%m/%Y")
                                        data_contrat["date_signature"] = "En attente de validation"
                                        data_contrat["signataire"] = "Direction (Non signé)"
                                        res = generer_contrat_pdf(data_contrat)
                                        pdf_bytes = res[1] if isinstance(res, tuple) else res

                            # CAS 2 : BON DE CAISSE / PAIEMENT / ACOMPTE / ENGAGEMENT DETTE
                            elif doc_type in ['bon_caisse', 'bon_paiement', 'acompte', 'engagement_dette', 'reglement_dette']:
                                # Extraire l'ID de l'achat depuis la référence (ex: PAY-1-LOT-...)
                                import re
                                match = re.search(r'PAY-(\d+)-', doc_ref)
                                if match:
                                    id_achat = int(match.group(1))
                                    achat_row = fetch_one("""
                                        SELECT a.id, a.date, f.nom AS fournisseur, 
                                            a.numero_de_lot AS num_lot, a.quantite_kg, 
                                            a.prix_unitaire, a.total, 
                                            a.montant_avance AS versement, 
                                            (a.total - a.montant_avance) AS reste, 
                                            a.statut, a.numero_contrat, 
                                            a.poids_brut, a.poids_net, 
                                            f.numero_de_compte AS compte,
                                            a.deductions, a.libelle_deductions
                                        FROM achats a
                                        LEFT JOIN fournisseurs f ON a.id_fournisseur = f.id
                                        WHERE a.id = %s
                                    """, (id_achat,))

                                    if achat_row:
                                        data_p = {
                                            "id": achat_row[0],
                                            "date": achat_row[1],
                                            "fournisseur": achat_row[2],
                                            "num_lot": achat_row[3],
                                            "quantite_kg": achat_row[4],
                                            "prix_unitaire": achat_row[5],
                                            "total": achat_row[6],
                                            "versement": achat_row[7],
                                            "reste": achat_row[8],
                                            "statut": achat_row[9],
                                            "num_contrat": achat_row[10],
                                            "poids_brut": achat_row[11],
                                            "poids_net": achat_row[12],
                                            "compte": achat_row[13],
                                            "deductions": achat_row[14],
                                            "libelle_deductions": achat_row[15]
                                        }
                                        if 'code_verification' in row:
                                            data_p['code_verification'] = row['code_verification']
                                        res = generer_bon_paiement_pdf(data_p, type_document=doc_type)
                                        pdf_bytes = res[1] if isinstance(res, tuple) else res
                            # CAS 3 : FACTURE DE VENTE
                            elif doc_type == 'facture_vente':
                                match = re.search(r"INV-(\d+)", doc_ref)
                                if match:
                                    id_vente = int(match.group(1))
                                    row_vente = fetch_one("""
                                        SELECT v.id, v.date_vente, c.nom, c.email, c.pays, c.nui, 
                                               v.quantite_kg, v.prix_unitaire, v.total, v.devise,
                                               v.incoterm, v.port_embarquement, v.port_dechargement, v.termes_paiement
                                        FROM ventes v
                                        JOIN clients c ON v.id_client = c.id
                                        WHERE v.id = %s
                                    """, (id_vente,))
                                    if row_vente:
                                        # Récupération des colonnes
                                        df_vente = get_dataframe_from_query("""
                                            SELECT v.id, v.date_vente, c.nom, c.email, c.pays, c.nui, 
                                                   v.quantite_kg, v.prix_unitaire, v.total, v.devise,
                                                   v.incoterm, v.port_embarquement, v.port_dechargement, v.termes_paiement
                                            FROM ventes v
                                            JOIN clients c ON v.id_client = c.id
                                            WHERE v.id = %s
                                        """, (id_vente,))
                                        if not df_vente.empty:
                                            data_vente = df_vente.iloc[0].to_dict()
                                            client_info = {
                                                "nom": data_vente['nom'],
                                                "email": data_vente['email'],
                                                "pays": data_vente['pays'],
                                                "nui": data_vente['nui']
                                            }
                                            nom_fichier = generer_pdf_international(
                                                id_doc=data_vente['id'],
                                                date_str=data_vente['date_vente'].strftime('%Y-%m-%d'),
                                                client=client_info,
                                                qte=data_vente['quantite_kg'],
                                                pu=data_vente['prix_unitaire'],
                                                total=data_vente['total'],
                                                devise=data_vente['devise'],
                                                incoterm=data_vente['incoterm'],
                                                port_depart=data_vente['port_embarquement'],
                                                port_arrivee=data_vente['port_dechargement'] or "",
                                                condition_paiement=data_vente['termes_paiement'],
                                                banque_nom="", banque_swift="", banque_iban="",
                                                cachet_blob=None
                                            )
                                            if nom_fichier and os.path.exists(nom_fichier):
                                                with open(nom_fichier, "rb") as f:
                                                    pdf_bytes = f.read()
                                                os.remove(nom_fichier)

                        except Exception as e:
                            st.error(f"❌ Erreur lors de la préparation du document : {e}")

                        # -----------------------------------------------------
                        # 2. INFORMATIONS & BOUTONS D'ACTION
                        # -----------------------------------------------------
                        c_info, c_action = st.columns([3, 2])

                        with c_info:
                            st.markdown(
                                f"""
                                <div style="
                                    background: #1e293b;
                                    border-radius: 10px;
                                    padding: 14px 16px;
                                    border: 1px solid #334155;
                                ">
                                    <div style="font-size: 13px; color: #94a3b8; margin-bottom: 8px;">
                                        👤 <b style="color:#e2e8f0;">Émis par :</b> {row['demandeur']}
                                    </div>
                                    <div style="font-size: 13px; color: #94a3b8; margin-bottom: 8px;">
                                        📅 <b style="color:#e2e8f0;">Date de demande :</b> {row['date_creation']}
                                    </div>
                                    <div style="font-size: 13px; color: #94a3b8;">
                                        📝 <b style="color:#e2e8f0;">Objet :</b> {row['description']}
                                    </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                        with c_action:
                            st.markdown("**🖋️ Validation Direction**")

                            role_signataire = st.selectbox(
                                "Apposer le cachet de :",
                                roles_existants,
                                key=f"role_{row['id']}"
                            )
                            
                            motif_rejet = st.text_area(
                                    "Motif du rejet (si rejet)",
                                    placeholder="Précisez la raison du rejet...",
                                    key=f"motif_{row['id']}",
                                    help="Ce champ est facultatif si vous validez, mais obligatoire pour rejeter."
                                )
                            
                            col_b1, col_b2 = st.columns(2)

                            with col_b1:
                                if st.button("✅ Valider", key=f"btn_sign_{row['id']}", type="primary", use_container_width=True):
                                    try:
                                        # 1. Récupération du cachet
                                        cachet_blob = None
                                        if role_signataire:
                                            res_cachet = fetch_one(
                                                "SELECT fichier_cachet FROM cachets_direction WHERE role_signataire = %s",
                                                (role_signataire,)
                                            )
                                            if res_cachet:
                                                cachet_blob = res_cachet[0]  # bytes

                                        code_verif = generer_code_verification()
                                        pdf_bytes = None
                                        doc_type = row['type_doc']
                                        doc_ref = row['reference']

                                        # =====================================================
                                        # 2. TOUJOURS régénérer le PDF avec le cachet
                                        # =====================================================
                                        if doc_type == 'contrat':
                                            df_contrat = get_dataframe_from_query("""
                                                SELECT c.*, f.nom AS fournisseur, f.telephone, f.ville, f.adresse,
                                                       f.Rccm, f.NUI, f.numero_de_compte
                                                FROM contrats c
                                                LEFT JOIN fournisseurs f ON c.id_fournisseur = f.id
                                                WHERE c.numero_contrat = %s
                                            """, (doc_ref,))
                                            if not df_contrat.empty:
                                                data_contrat = df_contrat.iloc[0].to_dict()
                                                data_contrat["num"] = data_contrat.get("numero_contrat", doc_ref)
                                                data_contrat["qte"] = data_contrat.get("quantite_prevue", data_contrat.get("quantite", 0))
                                                data_contrat["pu"] = data_contrat.get("prix_unitaire", 0)
                                                data_contrat["delai"] = data_contrat.get("delai_livraison", "N/A")
                                                data_contrat["lieu"] = data_contrat.get("lieu_livraison", "N/A")
                                                data_contrat["date"] = datetime.now().strftime("%d/%m/%Y")
                                                data_contrat["date_signature"] = datetime.now().strftime("%d/%m/%Y à %H:%M")
                                                data_contrat["signataire"] = role_signataire
                                                res = generer_contrat_pdf(data_contrat, cachet_blob=cachet_blob)
                                                pdf_bytes = res[1] if isinstance(res, tuple) else res

                                        elif doc_type in ['bon_caisse', 'bon_paiement', 'engagement_dette', 'acompte']:
                                            df_p = get_dataframe_from_query("""
                                                SELECT a.id, a.date, f.nom AS fournisseur, a.numero_de_lot AS num_lot,
                                                       a.quantite_kg, a.prix_unitaire, a.total, a.montant_avance AS versement,
                                                       (a.total - a.montant_avance) AS reste, a.statut, a.numero_contrat,
                                                       a.poids_brut, a.poids_net, f.numero_de_compte AS compte,
                                                       a.deductions, a.libelle_deductions
                                                FROM achats a
                                                LEFT JOIN fournisseurs f ON a.id_fournisseur = f.id
                                                WHERE a.numero_de_lot = %s OR CAST(a.id AS TEXT) = %s OR %s LIKE '%%' || a.numero_de_lot || '%%'
                                                ORDER BY a.id DESC LIMIT 1
                                            """, (doc_ref, doc_ref, doc_ref))
                                            if not df_p.empty:
                                                data_p = df_p.iloc[0].to_dict()
                                                data_p["num_paiement"] = doc_ref
                                                data_p["total"] = float(data_p.get("total") or 0.0)
                                                data_p["versement"] = float(data_p.get("versement") or 0.0)
                                                data_p["reste"] = float(data_p.get("reste") or 0.0)
                                                data_p["quantite_kg"] = float(data_p.get("quantite_kg") or 0.0)
                                                data_p["prix_unitaire"] = float(data_p.get("prix_unitaire") or 0.0)
                                                data_p["poids_net"] = float(data_p.get("poids_net") or 0.0)
                                                data_p["code_verification"] = code_verif
                                                data_p["code_verif"] = code_verif
                                                res = generer_bon_paiement_pdf(
                                                    data_p,
                                                    type_document=doc_type,
                                                    cachet_blob=cachet_blob
                                                )
                                                pdf_bytes = res[1] if isinstance(res, tuple) else res

                                        elif doc_type == 'reglement_dette':
                                            match = re.search(r"REG-(\d+)-", doc_ref)
                                            if match:
                                                id_achat = int(match.group(1))
                                                df_p = get_dataframe_from_query("""
                                                    SELECT a.id, a.date, f.nom AS fournisseur, a.numero_de_lot AS num_lot,
                                                           a.quantite_kg, a.prix_unitaire, a.total, a.montant_avance,
                                                           a.numero_contrat, a.poids_brut, a.poids_net, f.numero_de_compte AS compte,
                                                           a.deductions, a.libelle_deductions
                                                    FROM achats a
                                                    LEFT JOIN fournisseurs f ON a.id_fournisseur = f.id
                                                    WHERE a.id = %s
                                                """, (id_achat,))
                                                if not df_p.empty:
                                                    data_p = df_p.iloc[0].to_dict()
                                                    data_p["num_paiement"] = doc_ref
                                                    montant_regle = float(row['montant'] or 0.0)
                                                    total_achat = float(data_p.get("total") or 0.0)
                                                    avance_actuelle = float(data_p.get("montant_avance") or 0.0)
                                                    avance_avant = max(0.0, avance_actuelle - montant_regle)
                                                    dette_initiale = max(0.0, total_achat - avance_avant)
                                                    data_p["dette_initiale"] = dette_initiale
                                                    data_p["montant_regle"] = montant_regle
                                                    data_p["versement"] = montant_regle
                                                    data_p["reste"] = max(0.0, dette_initiale - montant_regle)
                                                    res = generer_bon_paiement_pdf(data_p, type_document='reglement_dette')
                                                    pdf_bytes = res[1] if isinstance(res, tuple) else res

                                        elif doc_type == 'facture_vente':
                                            match = re.search(r"INV-(\d+)", doc_ref)
                                            if match:
                                                id_vente = int(match.group(1))
                                                df_vente = get_dataframe_from_query("""
                                                    SELECT v.id, v.date_vente, c.nom, c.email, c.pays, c.nui,
                                                           v.quantite_kg, v.prix_unitaire, v.total, v.devise,
                                                           v.incoterm, v.port_embarquement, v.port_dechargement, v.termes_paiement
                                                    FROM ventes v
                                                    JOIN clients c ON v.id_client = c.id
                                                    WHERE v.id = %s
                                                """, (id_vente,))
                                                if not df_vente.empty:
                                                    data_vente = df_vente.iloc[0].to_dict()
                                                    client_info = {
                                                        "nom": data_vente['nom'],
                                                        "email": data_vente['email'],
                                                        "pays": data_vente['pays'],
                                                        "nui": data_vente['nui']
                                                    }
                                                    nom_fichier = generer_pdf_international(
                                                        id_doc=data_vente['id'],
                                                        date_str=data_vente['date_vente'].strftime('%Y-%m-%d'),
                                                        client=client_info,
                                                        qte=data_vente['quantite_kg'],
                                                        pu=data_vente['prix_unitaire'],
                                                        total=data_vente['total'],
                                                        devise=data_vente['devise'],
                                                        incoterm=data_vente['incoterm'],
                                                        port_depart=data_vente['port_embarquement'],
                                                        port_arrivee=data_vente['port_dechargement'] or "",
                                                        condition_paiement=data_vente['termes_paiement'],
                                                        banque_nom="", banque_swift="", banque_iban="",
                                                        cachet_blob=cachet_blob
                                                    )
                                                    if nom_fichier and os.path.exists(nom_fichier):
                                                        with open(nom_fichier, "rb") as f:
                                                            pdf_bytes = f.read()
                                                        os.remove(nom_fichier)

                                        # 3. Appliquer le QR code
                                        if pdf_bytes:
                                            pdf_bytes_final = apposer_qr_sur_pdf(pdf_bytes, code_verif, row['reference'])
                                            hash_final = calculer_hash_pdf(pdf_bytes_final)
                                        else:
                                            raise Exception("Impossible de générer le PDF avec cachet")

                                        # 4. Mise à jour en base
                                        with conn.cursor() as cur:
                                            cur.execute("""
                                                UPDATE documents_generes
                                                SET statut = 'VALIDE',
                                                  signataire = %s,
                                                  date_signature = CURRENT_TIMESTAMP,
                                                  pdf_hash = %s,
                                                  code_verification = %s,
                                                  fichier_pdf = %s
                                                WHERE id = %s
                                            """, (role_signataire, hash_final, code_verif, pdf_bytes_final, row['id']))
                                            if row['type_doc'] == 'contrat':
                                                cur.execute("""
                                                    UPDATE contrats
                                                    SET statut = 'VALIDE', signataire = %s, date_signature = CURRENT_TIMESTAMP
                                                    WHERE numero_contrat = %s
                                                """, (role_signataire, row['reference']))
                                            conn.commit()
                                        st.toast(f"✅ Document {row['reference']} validé et authentifié (code: {code_verif})", icon="✅")
                                        st.rerun()

                                    except Exception as e:
                                        st.error(f"Erreur lors de la validation : {e}")
                            
                            with col_b2:
                                if st.button("❌ Rejeter", key=f"btn_reject_{row['id']}", use_container_width=True):
                                    # Vérifier que le motif est renseigné
                                    if not motif_rejet.strip():
                                        st.error("❌ Veuillez indiquer un motif pour le rejet.")
                                    else:
                                        try:
                                            # Mise à jour du document
                                            with conn.cursor() as cur:
                                                # On met à jour le statut, signataire, date et on ajoute le motif à la description
                                                nouvelle_description = f"{row['description']} (REJETÉ : {motif_rejet.strip()})"
                                                cur.execute("""
                                                    UPDATE documents_generes
                                                    SET statut = 'REJETE',
                                                        signataire = %s,
                                                        date_signature = CURRENT_TIMESTAMP,
                                                        description = %s
                                                    WHERE id = %s
                                                """, (role_signataire, nouvelle_description, row['id']))

                                                # Si c'est un contrat, on met aussi son statut à 'ANNULE' (ou 'REJETE')
                                                if row['type_doc'] == 'contrat':
                                                    cur.execute("""
                                                        UPDATE contrats
                                                        SET statut = 'ANNULE', signataire = %s
                                                        WHERE numero_contrat = %s
                                                    """, (role_signataire, row['reference']))

                                                conn.commit()

                                            # Journalisation
                                            log_action(f"Document {row['reference']} rejeté par {role_signataire} - Motif : {motif_rejet.strip()}")

                                            st.toast(f"❌ Document {row['reference']} rejeté.", icon="❌")
                                            st.rerun()

                                        except Exception as e:
                                            st.error(f"Erreur lors du rejet : {e}")

                        # -----------------------------------------------------
                        # 3. ZONE D'APERÇU DU DOCUMENT
                        # -----------------------------------------------------
                        st.divider()
                        st.markdown("**👁️ Aperçu du document avant validation**")

                        if pdf_bytes:
                            afficher_pdf(pdf_bytes)
                        else:
                            st.info("ℹ️ Aperçu non disponible pour ce document.")

    # =========================================================================
    # ONGLET 2 : ARCHIVES ET HISTORIQUE
    # =========================================================================
    with tab_archives:
        st.markdown("#### 📂 Historique des actes traités")

        try:
            df_valides = get_dataframe_from_query("""
                SELECT type_doc as "Type", reference as "Référence", montant as "Montant (FCFA)", 
                       demandeur as "Demandeur", statut as "Statut", signataire as "Signataire", 
                       date_signature as "Date Traitement"
                FROM documents_generes 
                WHERE statut != 'EN_ATTENTE' 
                ORDER BY date_signature DESC
            """)

            if df_valides.empty:
                st.info("ℹ️ Aucun historique disponible pour le moment.")
            else:
                filtre_ref = st.text_input(
                    "🔎 Filtrer par référence ou demandeur",
                    placeholder="Tapez une référence ou un nom..."
                )
                if filtre_ref:
                    df_valides = df_valides[
                        df_valides["Référence"].str.contains(filtre_ref, case=False, na=False) |
                        df_valides["Demandeur"].str.contains(filtre_ref, case=False, na=False)
                    ]

                col_a1, col_a2, col_a3 = st.columns(3)
                with col_a1:
                    st.metric("📄 Total traités", len(df_valides))
                with col_a2:
                    nb_valides = (df_valides["Statut"] == "VALIDE").sum()
                    st.metric("✅ Validés", int(nb_valides))
                with col_a3:
                    nb_rejetes = (df_valides["Statut"] == "REJETE").sum()
                    st.metric("❌ Rejetés", int(nb_rejetes))

                st.markdown("<br>", unsafe_allow_html=True)

                st.dataframe(
                    df_valides,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Montant (FCFA)": st.column_config.NumberColumn(format="%d FCFA")
                    }
                )
        except Exception as e:
            st.error(f"❌ Erreur lors du chargement des archives : {e}")

    # =========================================================================
    # ONGLET 3 : GESTION DYNAMIQUE DES CACHETS
    # =========================================================================
    with tab_cachets:
        st.markdown("#### ⚙️ Configurer les cachets numériques")
        st.caption("Gérez ici les tampons officiels de l'entreprise (Format requis : **PNG avec fond transparent**).")

        with st.container(border=True):
            st.markdown("**➕ Enregistrer un nouveau cachet / tampon**")
            with st.form("form_upload_cachet", clear_on_submit=True):
                col_form1, col_form2 = st.columns(2)

                with col_form1:
                    nouveau_role = st.text_input(
                        "Titre du signataire *",
                        placeholder="Ex: DG, DGA, DRH, DAF..."
                    )
                with col_form2:
                    fichier_upload = st.file_uploader(
                        "Image du cachet (PNG transparent) *",
                        type=["png"]
                    )

                submit_cachet = st.form_submit_button(
                    "💾 Enregistrer le cachet",
                    type="primary",
                    use_container_width=True
                )

                if submit_cachet:
                    if not nouveau_role:
                        st.error("❌ Veuillez renseigner le titre du signataire.")
                    elif not fichier_upload:
                        st.error("❌ Veuillez sélectionner un fichier PNG.")
                    else:
                        role_propre = nouveau_role.strip().upper()
                        img_bytes = fichier_upload.read()

                        try:
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM cachets_direction WHERE role_signataire = %s", (role_propre,))
                                cur.execute("""
                                    INSERT INTO cachets_direction (role_signataire, fichier_cachet)
                                    VALUES (%s, %s)
                                """, (role_propre, img_bytes))
                                conn.commit()
                            st.toast(f"✅ Cachet du rôle '{role_propre}' enregistré !", icon="✅")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de l'enregistrement : {e}")

        st.divider()
        st.markdown("#### 🏛️ Répertoire des cachets actifs")

        try:
            cachets_enregistres = fetch_all("SELECT role_signataire, fichier_cachet FROM cachets_direction ORDER BY role_signataire")

            if not cachets_enregistres:
                st.info("ℹ️ Aucun cachet n'est encore enregistré dans le système.")
            else:
                colonnes_grille = st.columns(3)
                for index, (role, img_blob) in enumerate(cachets_enregistres):
                    with colonnes_grille[index % 3]:
                        with st.container(border=True):
                            st.markdown(
                                f"""
                                <div style="text-align:center; font-size:15px; font-weight:700; color:#f8fafc; margin-bottom:8px;">
                                    🛡️ {role}
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                            if img_blob:
                                # Convertir le blob en bytes si nécessaire (memoryview -> bytes)
                                if isinstance(img_blob, memoryview):
                                    img_bytes = img_blob.tobytes()
                                else:
                                    img_bytes = img_blob
                                # Utiliser io.BytesIO pour afficher l'image
                                import io
                                try:
                                    st.image(io.BytesIO(img_bytes), use_container_width=True)
                                except Exception as e:
                                    st.warning(f"Impossible d'afficher l'image pour {role}: {e}")
                            else:
                                st.warning("⚠️ Fichier image manquant")

                            st.markdown("<br>", unsafe_allow_html=True)
                            if st.button("🗑️ Retirer", key=f"del_cachet_{role}", use_container_width=True):
                                try:
                                    with conn.cursor() as cur:
                                        cur.execute("DELETE FROM cachets_direction WHERE role_signataire = %s", (role,))
                                        conn.commit()
                                    st.toast(f"🗑️ Cachet '{role}' supprimé.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Erreur de suppression : {e}")
        except Exception as e:
            st.error(f"❌ Impossible de charger le répertoire des cachets : {e}")

    # =========================================================================
    # ONGLET 4 : VÉRIFICATION D'AUTHENTICITÉ
    # =========================================================================
    with tab_verif:
        st.markdown("#### 🔍 Vérifier l'authenticité d'un document")
        st.caption("Entrez la référence et le code de vérification imprimés sur le document (à côté du QR code).")

        col_v1, col_v2 = st.columns(2)
        with col_v1:
            ref_saisie = st.text_input("Référence du document", placeholder="Ex: CONTRAT-2026-014")
        with col_v2:
            code_saisi = st.text_input("Code de vérification", placeholder="Ex: A1B2C3D4").strip().upper()

        if st.button("🔎 Vérifier", type="primary"):
            if not ref_saisie or not code_saisi:
                st.warning("⚠️ Veuillez renseigner la référence et le code.")
            else:
                try:
                    resultat = fetch_one("""
                        SELECT type_doc, reference, montant, demandeur, signataire, date_signature, code_verification, statut
                        FROM documents_generes
                        WHERE reference = %s
                    """, (ref_saisie.strip(),))

                    if not resultat:
                        st.error("❌ Aucun document trouvé avec cette référence.")
                    elif resultat[6] != code_saisi:
                        st.error("🚫 Code de vérification incorrect. Ce document pourrait être falsifié ou modifié.")
                    else:
                        st.success("✅ Document authentique et non modifié.")
                        montant_format = f"{resultat[2]:,.0f}" if resultat[2] is not None else "0"
                        st.markdown(
                            f"""
                            - **Type :** {resultat[0]}
                            - **Référence :** {resultat[1]}
                            - **Montant :** {montant_format} FCFA
                            - **Demandeur :** {resultat[3]}
                            - **Validé par :** {resultat[4]}
                            - **Date de signature :** {resultat[5]}
                            - **Statut :** {resultat[7]}
                            """
                        )
                except Exception as e:
                    st.error(f"❌ Erreur lors de la vérification : {e}")
                    
elif choix == "⚙️ Administration & Backup":
    # --- En-tête de page ---
    st.markdown(
        """
        <div style="
            background: linear-gradient(135deg, #1e293b, #0f172a);
            border-radius: 16px;
            padding: 24px 28px;
            margin-bottom: 20px;
            border: 1px solid #334155;
        ">
            <div style="font-size: 26px; font-weight: 800; color: #f8fafc;">
                ⚙️ Administration & Backup
            </div>
            <div style="font-size: 14px; color: #94a3b8; margin-top: 4px;">
                Zone réservée aux administrateurs · Sauvegarde, journal d'activité et gestion des comptes
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.warning("🔒 Zone réservée aux Administrateurs.")

    # --- Onglets principaux : Sauvegarde | Journal | Comptes ---
    tab_backup, tab_logs = st.tabs(["💾 Sauvegarde", "📋 Journal d'activité"])

    # ---- ONGLET 1 : SAUVEGARDE ----
    with tab_backup:
        st.markdown("#### 💾 Copie de sauvegarde de la base de données")
        st.caption("Téléchargez une copie complète et horodatée de votre base de données.")

        st.info("ℹ️ Avec la migration vers Supabase, la sauvegarde se fait via l'interface de Supabase (Settings > Database > Backups).")
        st.info("💡 Vous pouvez aussi utiliser `pg_dump` pour exporter votre base PostgreSQL.")

        if os.path.exists("gestion_cacao.db"):
            taille_mo = os.path.getsize("gestion_cacao.db") / (1024 * 1024)
            date_maj = datetime.fromtimestamp(os.path.getmtime("gestion_cacao.db")).strftime("%d/%m/%Y à %H:%M")

            col_info1, col_info2, col_info3 = st.columns(3)
            with col_info1:
                st.metric("📦 Taille", f"{taille_mo:.2f} Mo")
            with col_info2:
                st.metric("🕒 Dernière modification", date_maj)
            with col_info3:
                st.metric("📁 Format", "SQLite (.db)")

            st.markdown("<br>", unsafe_allow_html=True)

            with open("gestion_cacao.db", "rb") as f:
                st.download_button(
                    "☁️ Exporter l'intégralité de la base de données",
                    f.read(),
                    f"backup_gestion_cacao_{datetime.now().strftime('%Y%m%d_%H%M')}.db",
                    use_container_width=True,
                    type="primary"
                )
        else:
            st.info("💡 Aucun fichier SQLite local trouvé. La base de données est désormais hébergée sur Supabase.")

    # ---- ONGLET 2 : JOURNAL ----
    with tab_logs:
        st.markdown("#### 📋 Journal des actions récentes")
        st.caption("Les 50 dernières actions enregistrées dans le système.")

        logs_df = get_dataframe_from_query("SELECT * FROM logs ORDER BY id DESC LIMIT 50")

        if not logs_df.empty:
            st.dataframe(logs_df, use_container_width=True, hide_index=True)
        else:
            st.info("Aucune action enregistrée pour le moment.")

    # --- SÉCURITÉ COMPLÉMENTAIRE POUR LA GESTION DES DROITS ---
    if st.session_state.role == "Admin":
        st.divider()
        st.markdown(
            """
            <div style="font-size: 20px; font-weight: 700; color: #f8fafc; margin-bottom: 4px;">
                👥 Gestion Avancée des Comptes & Permissions
            </div>
            <div style="font-size: 13px; color: #94a3b8; margin-bottom: 16px;">
                Contrôle d'accès basé sur les rôles (RBAC)
            </div>
            """,
            unsafe_allow_html=True
        )

        tab_creer, tab_gerer = st.tabs(["➕ Créer un utilisateur", "⚙️ Gérer les comptes existants"])

        ONGLETS_DISPONIBLES = [
            "🏠 Tableau de Bord",
            "📦 Mouvements de Stock",
            "🧾 Achats (Entrees)",
            "🛍️ Ventes (Sorties)",
            "👥 Clients",
            "🤝 Fournisseurs",
            "🏗️ Prestataires & Transitaires",
            "📝 Contrats",
            "🏪 Magasins",
            "👑 Espace Direction",
            "⚙️ Administration & Backup"
        ]

        # ---- SOUS-ONGLET 1 : CRÉATION AVEC PERMISSIONS ----
        with tab_creer:
            st.markdown("##### 🆕 Nouveau compte utilisateur")

            with st.form("form_nouvel_utilisateur", clear_on_submit=True):
                col1, col2 = st.columns(2)
                with col1:
                    nouvel_identifiant = st.text_input(
                        "🔑 Identifiant de connexion",
                        placeholder="ex: acheteur_nord"
                    )
                    nom_affichage = st.text_input(
                        "🪪 Nom complet / Libellé",
                        placeholder="ex: Acheteur Grand-Nord"
                    )
                with col2:
                    nouveau_mdp = st.text_input("🔒 Mot de passe initial", type="password")
                    nouveau_role = st.selectbox("🎖️ Rôle sur l'application", ["Employe", "Admin"])

                st.markdown("**🔑 Limiter les onglets accessibles :**")
                onglets_selectionnes = st.multiselect(
                    "Cochez les onglets autorisés pour cet utilisateur",
                    options=ONGLETS_DISPONIBLES,
                    default=["🏠 Tableau de Bord", "📦 Mouvements de Stock", "🧾 Achats (Entrees)"],
                    label_visibility="collapsed"
                )

                st.markdown("<br>", unsafe_allow_html=True)
                bouton_creer = st.form_submit_button(
                    "✅ Créer l'utilisateur avec restrictions",
                    use_container_width=True,
                    type="primary"
                )

            if bouton_creer:
                if not nouvel_identifiant or not nouveau_mdp or not nom_affichage:
                    st.error("❌ Veuillez remplir tous les champs du formulaire.")
                elif not onglets_selectionnes:
                    st.error("❌ Veuillez autoriser au moins un onglet d'accès.")
                else:
                    hash_mdp_neuf = hashlib.sha256(nouveau_mdp.encode()).hexdigest()
                    permissions_str = ",".join(onglets_selectionnes)

                    try:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO utilisateurs (username, password_hash, role, label, permissions)
                                VALUES (%s, %s, %s, %s, %s)
                            """, (nouvel_identifiant.strip(), hash_mdp_neuf, nouveau_role, nom_affichage.strip(), permissions_str))
                            conn.commit()
                        st.success(f"✅ Le compte pour '{nom_affichage}' a été créé avec ses droits spécifiques !")
                        st.rerun()
                    except Exception as e:
                        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
                            st.error("❌ Cet identifiant existe déjà. Veuillez en choisir un autre.")
                        else:
                            st.error(f"❌ Erreur lors de l'enregistrement : {e}")

        # ---- SOUS-ONGLET 2 : MODIFIER / SUPPRIMER UN COMPTE ----
        with tab_gerer:
            utilisateurs_existants = fetch_all("SELECT username, role, label, permissions FROM utilisateurs")
            dict_users = {f"{u[2]} ({u[0]} - {u[1]})": u for u in utilisateurs_existants}

            if dict_users:
                st.markdown("##### 🔍 Sélection du compte")
                user_selected_label = st.selectbox(
                    "Sélectionnez le compte à modifier :",
                    list(dict_users.keys()),
                    label_visibility="collapsed"
                )
                user_data = dict_users[user_selected_label]

                u_username = user_data[0]
                u_role = user_data[1]
                u_label = user_data[2]
                u_permissions_raw = user_data[3]

                role_color = "#ef4444" if u_role == "Admin" else "#22c55e"
                st.markdown(
                    f"""
                    <div style="
                        display: inline-block;
                        background: {role_color}22;
                        color: {role_color};
                        border: 1px solid {role_color}55;
                        border-radius: 20px;
                        padding: 4px 14px;
                        font-size: 12px;
                        font-weight: 700;
                        margin: 8px 0 16px 0;
                    ">
                        {'🔴' if u_role == 'Admin' else '🟢'} {u_role}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                if u_permissions_raw:
                    u_perms_list = [p.strip() for p in u_permissions_raw.split(",") if p.strip() in ONGLETS_DISPONIBLES]
                else:
                    if u_role == "Admin":
                        u_perms_list = ONGLETS_DISPONIBLES.copy()
                    else:
                        u_perms_list = [o for o in ONGLETS_DISPONIBLES if o != "⚙️ Administration & Backup"]

                with st.form(f"form_modif_utilisateur_{u_username}"):
                    st.markdown(f"**⚙️ Paramètres du compte : `{u_username}`**")
                    col_m1, col_m2 = st.columns(2)
                    with col_m1:
                        nouveau_lbl = st.text_input("🪪 Nom complet / Libellé", value=u_label)
                        nouveau_r = st.selectbox("🎖️ Rôle", ["Employe", "Admin"], index=0 if u_role == "Employe" else 1)
                    with col_m2:
                        nouveau_mdp_edit = st.text_input(
                            "🔒 Nouveau mot de passe",
                            type="password",
                            placeholder="Laisser vide pour inchangé"
                        )

                    st.markdown("**🔒 Ajuster les onglets accessibles :**")
                    nouvelles_perms = st.multiselect(
                        "Onglets autorisés",
                        options=ONGLETS_DISPONIBLES,
                        default=u_perms_list,
                        label_visibility="collapsed"
                    )

                    st.markdown("<br>", unsafe_allow_html=True)
                    col_btn_edit1, col_btn_edit2 = st.columns(2)
                    with col_btn_edit1:
                        bouton_enregistrer_modif = st.form_submit_button(
                            "💾 Enregistrer les modifications",
                            use_container_width=True,
                            type="primary"
                        )
                    with col_btn_edit2:
                        is_self = (st.session_state.get("username_id") == u_username or u_username == "ADG")
                        bouton_supprimer = st.form_submit_button(
                            "🗑️ Supprimer définitivement le compte",
                            use_container_width=True,
                            disabled=is_self
                        )

                    if is_self:
                        st.caption("⚠️ Ce compte est protégé et ne peut pas être supprimé (compte connecté ou compte fondateur).")

                if bouton_enregistrer_modif:
                    if not nouveau_lbl:
                        st.error("❌ Le nom complet ne peut pas être vide.")
                    elif not nouvelles_perms:
                        st.error("❌ L'utilisateur doit avoir accès à au moins un onglet.")
                    else:
                        perms_str = ",".join(nouvelles_perms)
                        try:
                            with conn.cursor() as cur:
                                if nouveau_mdp_edit:
                                    hash_nouveau_mdp = hashlib.sha256(nouveau_mdp_edit.encode()).hexdigest()
                                    cur.execute("""
                                        UPDATE utilisateurs 
                                        SET label = %s, role = %s, password_hash = %s, permissions = %s
                                        WHERE username = %s
                                    """, (nouveau_lbl.strip(), nouveau_r, hash_nouveau_mdp, perms_str, u_username))
                                else:
                                    cur.execute("""
                                        UPDATE utilisateurs 
                                        SET label = %s, role = %s, permissions = %s
                                        WHERE username = %s
                                    """, (nouveau_lbl.strip(), nouveau_r, perms_str, u_username))
                                conn.commit()
                            log_action(f"Modification utilisateur {u_username} (Rôle: {nouveau_r}, Perms: {perms_str})")
                            st.success(f"✅ Compte '{u_username}' mis à jour avec succès !")
                            st.rerun()
                        except Exception as e:
                            st.error(f"❌ Erreur lors de la mise à jour : {e}")

                if bouton_supprimer:
                    try:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM utilisateurs WHERE username = %s", (u_username,))
                            conn.commit()
                        log_action(f"Suppression du compte utilisateur {u_username}")
                        st.success(f"🗑️ Le compte `{u_username}` a été supprimé.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Erreur lors de la suppression : {e}")
            else:
                st.info("Aucun compte utilisateur trouvé.")
                
# FIN DE L'APPLICATION
# ==========================================