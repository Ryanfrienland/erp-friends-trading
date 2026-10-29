# qr_verifier.py
import streamlit as st
import psycopg2

def verifier_document_qr(ref, code):
    try:
        _conn = psycopg2.connect(st.secrets["supabase"]["db_url"], sslmode="require")
        with _conn.cursor() as cur:
            cur.execute("""
                SELECT type_doc, reference, montant, demandeur, signataire,
                       date_signature, statut, pdf_hash, code_verification
                FROM documents_generes
                WHERE reference = %s
                ORDER BY id DESC LIMIT 1
            """, (ref,))
            row = cur.fetchone()
        _conn.close()
        return row
    except Exception as e:
        print(f"Erreur DB QR : {e}")
        return None

def afficher_page_verification():
    qp = st.query_params
    if "verify_ref" not in qp or "verify_code" not in qp:
        return  # Pas de vérification demandée
    
    ref_qr = qp["verify_ref"]
    code_qr = qp["verify_code"]

    st.markdown("""
        <div style="background:linear-gradient(135deg,#1e293b,#0f172a);
                    padding:24px;border-radius:14px;margin-bottom:20px;">
            <h2 style="color:#f8fafc;margin:0;">🔍 Vérification d'authenticité</h2>
            <p style="color:#94a3b8;margin-top:6px;font-size:13px;">
                Document ERP — Friends Cameroon Commodities
            </p>
        </div>
    """, unsafe_allow_html=True)

    doc = verifier_document_qr(ref_qr, code_qr)

    if not doc:
        st.error(f"❌ Aucun document trouvé pour la référence **{ref_qr}**.")
    else:
        code_attendu = doc[8]
        if code_attendu != code_qr:
            st.error("🚫 **Code de vérification incorrect** — Document potentiellement falsifié.")
        else:
            st.success("✅ **Document authentique et non modifié.**")
            icones = {
                "bon_paiement": "📄", "bon_caisse": "💵",
                "engagement_dette": "📝", "reglement_dette": "💳",
                "contrat": "📜", "contrat_transport": "🚛",
                "facture_vente": "🧾",
            }
            icone = icones.get(doc[0], "📌")
            montant_format = f"{doc[2]:,.0f}" if doc[2] else "0"
            
            st.markdown(f"""
| Champ | Valeur |
|---|---|
| {icone} **Type** | {str(doc[0]).upper()} |
| **Référence** | {doc[1]} |
| **Montant** | {montant_format} FCFA |
| **Émis par** | {doc[3] or 'N/A'} |
| **Validé par** | {doc[4] or 'N/A'} |
| **Date signature** | {doc[5] or 'N/A'} |
| **Statut** | **{doc[6]}** |
| **Empreinte SHA-256** | `{(doc[7] or '')[:24]}…` |
            """)
            st.caption("🔒 Toute modification post-signature invaliderait cette vérification.")
    
    st.stop()
