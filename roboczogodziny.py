from datetime import datetime, date
import io
import os
import sqlite3
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
import streamlit as st

# Konfiguracja strony
st.set_page_config(
    page_title="Ewidencja Roboczogodzin i Rozliczenie Zlecenia",
    page_icon="⏱️",
    layout="wide",
)

DB_NAME = "roboczogodziny.db"

# Rejestracja czcionki Roboto z repozytorium dla poprawnych polskich znaków w PDF
FONT_NAME = "Helvetica"
FONT_BOLD_NAME = "Helvetica-Bold"

try:
  if os.path.exists("Roboto.ttf"):
    pdfmetrics.registerFont(TTFont("Roboto", "Roboto.ttf"))
    FONT_NAME = "Roboto"
    if os.path.exists("Roboto-Bold.ttf"):
      pdfmetrics.registerFont(TTFont("Roboto-Bold", "Roboto-Bold.ttf"))
      FONT_BOLD_NAME = "Roboto-Bold"
    else:
      FONT_BOLD_NAME = "Roboto"
except Exception:
  pass


# Inicjalizacja bazy danych SQLite z automatyczną aktualizacją struktur
def init_db():
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS zlecenia (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT,
            client_name TEXT,
            address TEXT,
            order_date TEXT,
            default_rate REAL,
            notes TEXT
        )
    """)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS pozycje_prac (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            zlecenie_id INTEGER,
            data_pracy TEXT,
            zakres_prac TEXT,
            godziny REAL,
            stawka REAL,
            FOREIGN KEY (zlecenie_id) REFERENCES zlecenia (id) ON DELETE CASCADE
        )
    """)
  try:
    cursor.execute("ALTER TABLE pozycje_prac ADD COLUMN data_pracy TEXT;")
  except sqlite3.OperationalError:
    pass
    
  conn.commit()
  conn.close()


init_db()


# Klasa do numerowania stron w PDF
class NumberedCanvas(canvas.Canvas):

  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._saved_page_states = []

  def showPage(self):
    self._saved_page_states.append(dict(self.__dict__))
    self._startPage()

  def save(self):
    num_pages = len(self._saved_page_states)
    for state in self._saved_page_states:
      self.__dict__.update(state)
      self.draw_page_number(num_pages)
      super().showPage()
    super().save()

  def draw_page_number(self, page_count):
    self.saveState()
    self.setFont(FONT_NAME, 8)
    self.setFillColorRGB(0.3, 0.3, 0.3)
    footer_text = (
        f"Strona {self._pageNumber} z {page_count}  |  Dokument wygenerowany"
        " elektronicznie"
    )
    self.drawRightString(A4[0] - 2 * cm, 1.5 * cm, footer_text)
    self.restoreState()


# Funkcja generująca PDF z roboczogodzin
def generate_pdf(
    client_data, tasks_data, total_hours, total_amount, default_rate
):
  buffer = io.BytesIO()
  doc = SimpleDocTemplate(
      buffer,
      pagesize=A4,
      rightMargin=2 * cm,
      leftMargin=2 * cm,
      topMargin=2 * cm,
      bottomMargin=2.0 * cm,
  )

  story = []
  styles = getSampleStyleSheet()

  title_style = ParagraphStyle(
      'DocTitle',
      parent=styles['Heading1'],
      fontName=FONT_BOLD_NAME,
      fontSize=18,
      leading=22,
      textColor='#1e293b',
      spaceAfter=6,
  )

  subtitle_style = ParagraphStyle(
      'DocSubtitle',
      parent=styles['Normal'],
      fontName=FONT_NAME,
      fontSize=10,
      leading=14,
      textColor='#64748b',
  )

  section_header = ParagraphStyle(
      'SectionHeader',
      parent=styles['Heading2'],
      fontName=FONT_BOLD_NAME,
      fontSize=12,
      leading=16,
      textColor='#0f172a',
      spaceBefore=10,
      spaceAfter=6,
  )

  cell_style = ParagraphStyle(
      'CellText',
      parent=styles['Normal'],
      fontName=FONT_NAME,
      fontSize=9,
      leading=12,
      textColor='#1e293b',
  )

  cell_header_style = ParagraphStyle(
      'CellHeaderText',
      parent=styles['Normal'],
      fontName=FONT_BOLD_NAME,
      fontSize=9,
      leading=12,
      textColor='#ffffff',
  )

  cell_right = ParagraphStyle('CellRight', parent=cell_style, alignment=2)
  cell_header_right = ParagraphStyle(
      'CellHeaderRight', parent=cell_header_style, alignment=2
  )

  # Nagłówek dokumentu
  story.append(Paragraph("Ewidencja Roboczogodzin", title_style))
  story.append(
      Paragraph(
          f"Data generowania: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
          subtitle_style,
      )
  )
  story.append(Spacer(1, 0.4 * cm))
  story.append(
      HRFlowable(
          width='100%', thickness=1.5, color='#cbd5e1', spaceAfter=15
      )
  )

  # Dane zlecenia i klienta w tabeli
  info_data = [
      [
          Paragraph("<b>Nazwa zlecenia:</b>", cell_style),
          Paragraph(client_data['project_name'], cell_style),
          Paragraph("<b>Data zlecenia:</b>", cell_style),
          Paragraph(str(client_data['date']), cell_style),
      ],
      [
          Paragraph("<b>Klient:</b>", cell_style),
          Paragraph(client_data['client_name'], cell_style),
          Paragraph("<b>Domyślna stawka:</b>", cell_style),
          Paragraph(f"{default_rate:.2f} PLN/h", cell_style),
      ],
      [
          Paragraph("<b>Adres realizacji:</b>", cell_style),
          Paragraph(client_data['address'], cell_style),
          Paragraph("<b>Uwagi:</b>", cell_style),
          Paragraph(client_data['notes'] or "Brak", cell_style),
      ],
  ]

  info_table = Table(info_data, colWidths=[3.5 * cm, 6.5 * cm, 3.5 * cm, 3.5 * cm])
  info_table.setStyle(
      TableStyle([
          ('VALIGN', (0, 0), (-1, -1), 'TOP'),
          ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
      ])
  )
  story.append(info_table)
  story.append(Spacer(1, 0.5 * cm))

  # Tabela wykonanych prac
  story.append(Paragraph("Szczegółowy zakres wykonanych prac", section_header))

  table_content = [[
      Paragraph("<b>Lp.</b>", cell_header_style),
      Paragraph("<b>Data</b>", cell_header_style),
      Paragraph("<b>Zakres / Opis wykonanych prac</b>", cell_header_style),
      Paragraph("<b>Ilość godz.</b>", cell_header_right),
      Paragraph("<b>Stawka (PLN)</b>", cell_header_right),
      Paragraph("<b>Wartość (PLN)</b>", cell_header_right),
  ]]

  for idx, row in enumerate(tasks_data, 1):
    val = row['Godziny'] * row['Stawka']
    table_content.append([
        Paragraph(str(idx), cell_style),
        Paragraph(str(row['Data']), cell_style),
        Paragraph(str(row['Zakres prac']), cell_style),
        Paragraph(f"{row['Godziny']:.2f}", cell_right),
        Paragraph(f"{row['Stawka']:.2f}", cell_right),
        Paragraph(f"{val:.2f}", cell_right),
    ])

  tasks_table = Table(
      table_content, colWidths=[1.0 * cm, 2.3 * cm, 6.2 * cm, 2.5 * cm, 2.5 * cm, 2.5 * cm]
  )
  tasks_table.setStyle(
      TableStyle([
          ('BACKGROUND', (0, 0), (-1, 0), '#334155'),
          ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
          ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
          ('TOPPADDING', (0, 0), (-1, -1), 5),
          ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
          ('GRID', (0, 0), (-1, -1), 0.5, '#cbd5e1'),
          ('ROWBACKGROUNDS', (0, 1), (-1, -1), ['#ffffff', '#f8fafc']),
      ])
  )
  story.append(tasks_table)
  story.append(Spacer(1, 0.6 * cm))

  # Podsumowanie kosztów
  summary_data = [
      [
          Paragraph("<b>Łączna liczba godzin:</b>", cell_style),
          Paragraph(f"<b>{total_hours:.2f} h</b>", cell_right),
      ],
      [
          Paragraph(
              "<b>Całkowity koszt robocizny (Do zapłaty):</b>",
              ParagraphStyle(
                  'BoldSum', parent=cell_style, fontName=FONT_BOLD_NAME
              ),
          ),
          Paragraph(
              f"<b>{total_amount:.2f} PLN</b>",
              ParagraphStyle(
                  'BoldSumR',
                  parent=cell_right,
                  fontName=FONT_BOLD_NAME,
                  fontSize=11,
              ),
          ),
      ],
  ]

  summary_table = Table(summary_data, colWidths=[11.5 * cm, 5.5 * cm])
  summary_table.setStyle(
      TableStyle([
          ('BACKGROUND', (0, 0), (-1, -1), '#f1f5f9'),
          ('BOX', (0, 0), (-1, -1), 1, '#94a3b8'),
          ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
          ('TOPPADDING', (0, 0), (-1, -1), 6),
          ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
          ('LEFTPADDING', (0, 0), (-1, -1), 8),
          ('RIGHTPADDING', (0, 0), (-1, -1), 8),
      ])
  )
  story.append(summary_table)

  doc.build(story, canvasmaker=NumberedCanvas)
  buffer.seek(0)
  return buffer.getvalue()


# Interfejs aplikacji Streamlit
st.title("⏱️ Ewidencja Roboczogodzin i Rozliczenie Zlecenia")

# Sidebar - Zarządzanie zleceniami (baza danych)
st.sidebar.header("📁 Baza Zleceń")


def get_all_zlecenia():
  conn = sqlite3.connect(DB_NAME)
  cursor = conn.cursor()
  cursor.execute("SELECT id, project_name, client_name, order_date FROM zlecenia ORDER BY id DESC")
  rows = cursor.fetchall()
  conn.close()
  return rows


zlecenia_list = get_all_zlecenia()
zlecenia_options = {"Nowe zlecenie / Wyczyść formularz": None}
for z in zlecenia_list:
  zlecenia_options[f"[{z[0]}] {z[1]} ({z[2]}) - {z[3]}"] = z[0]

selected_zlecenie_label = st.sidebar.selectbox("Wybierz zapisane zlecenie:", list(zlecenia_options.keys()))
selected_zlecenie_id = zlecenia_options[selected_zlecenie_label]

# Przycisk usuwania zlecenia w sidebarze (jeśli wybrano istniejące zlecenie)
if selected_zlecenie_id is not None:
  if st.sidebar.button("🗑️ Usuń to zlecenie z bazy", type="primary"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM zlecenia WHERE id = ?", (selected_zlecenie_id,))
    cursor.execute("DELETE FROM pozycje_prac WHERE zlecenie_id = ?", (selected_zlecenie_id,))
    conn.commit()
    conn.close()
    st.sidebar.success("Zlecenie zostało usunięte!")
    st.session_state['loaded_zlecenie_id'] = None
    st.rerun()

# Inicjalizacja stanu sesji
if 'loaded_zlecenie_id' not in st.session_state:
  st.session_state['loaded_zlecenie_id'] = None

# Obsługa wczytania zlecenia z bazy
if selected_zlecenie_id != st.session_state['loaded_zlecenie_id']:
  st.session_state['loaded_zlecenie_id'] = selected_zlecenie_id
  if selected_zlecenie_id is not None:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT project_name, client_name, address, order_date, default_rate, notes FROM zlecenia WHERE id = ?", (selected_zlecenie_id,))
    z_data = cursor.fetchone()

    cursor.execute("SELECT data_pracy, zakres_prac, godziny, stawka FROM pozycje_prac WHERE zlecenie_id = ?", (selected_zlecenie_id,))
    p_data = cursor.fetchall()
    conn.close()

    if z_data:
      st.session_state['project_name'] = z_data[0]
      st.session_state['client_name'] = z_data[1]
      st.session_state['address'] = z_data[2]
      try:
        st.session_state['order_date'] = datetime.strptime(z_data[3], "%Y-%m-%d").date()
      except:
        st.session_state['order_date'] = datetime.now().date()
      st.session_state['default_rate'] = z_data[4]
      st.session_state['notes'] = z_data[5]

      loaded_tasks = []
      for p in p_data:
        p_date_val = datetime.strptime(p[0], "%Y-%m-%d").date() if p[0] else datetime.now().date()
        loaded_tasks.append({"Data": p_date_val, "Zakres prac": p[1], "Godziny": p[2], "Stawka": p[3]})
      
      st.session_state['tasks_list'] = loaded_tasks
      st.rerun()
  else:
    st.session_state['project_name'] = "Montaż i uruchomienie instalacji"
    st.session_state['client_name'] = "Jan Kowalski"
    st.session_state['address'] = "ul. Przykładowa 1, Warszawa"
    st.session_state['order_date'] = datetime.now().date()
    st.session_state['default_rate'] = 100.0
    st.session_state['notes'] = ""
    today_str = datetime.now().date()
    st.session_state['tasks_list'] = [
        {"Data": today_str, "Zakres prac": "Pomiary i przygotowanie trasy kablowej", "Godziny": 3.0, "Stawka": 100.0},
        {"Data": today_str, "Zakres prac": "Montaż osprzętu i podłączenia", "Godziny": 5.0, "Stawka": 100.0},
    ]
    st.rerun()

# Ustawienia domyślne w session_state jeśli brak
if 'project_name' not in st.session_state:
  st.session_state['project_name'] = "Montaż i uruchomienie instalacji"
if 'client_name' not in st.session_state:
  st.session_state['client_name'] = "Jan Kowalski"
if 'address' not in st.session_state:
  st.session_state['address'] = "ul. Przykładowa 1, Warszawa"
if 'order_date' not in st.session_state:
  st.session_state['order_date'] = datetime.now().date()
if 'default_rate' not in st.session_state:
  st.session_state['default_rate'] = 100.0
if 'notes' not in st.session_state:
  st.session_state['notes'] = ""
if 'tasks_list' not in st.session_state:
  today_str = datetime.now().date()
  st.session_state['tasks_list'] = [
      {"Data": today_str, "Zakres prac": "Pomiary i przygotowanie trasy kablowej", "Godziny": 3.0, "Stawka": 100.0},
      {"Data": today_str, "Zakres prac": "Montaż osprzętu i podłączenia", "Godziny": 5.0, "Stawka": 100.0},
  ]

# Sekcja 1: Dane zlecenia
st.subheader("1. Informacje o zleceniu")
col1, col2, col3 = st.columns(3)

with col1:
  project_name = st.text_input("Nazwa zlecenia", value=st.session_state['project_name'])
  client_name = st.text_input("Klient", value=st.session_state['client_name'])

with col2:
  order_date = st.date_input("Data zlecenia", value=st.session_state['order_date'])
  default_rate = st.number_input("Domyślna stawka godzinowa (PLN)", min_value=0.0, value=float(st.session_state['default_rate']), step=10.0)

with col3:
  address = st.text_input("Adres realizacji", value=st.session_state['address'])
  notes = st.text_area("Uwagi / Notatki", value=st.session_state['notes'], height=68)

st.divider()

# Sekcja 2: Edytor pozycji prac
st.subheader("2. Zakres wykonanych prac i godziny")
st.markdown("Dodawaj, edytuj lub usuwaj pozycje zrealizowanych prac oraz wybieraj datę wykonania.")

df_tasks = pd.DataFrame(st.session_state['tasks_list'])
if 'Data' not in df_tasks.columns:
  df_tasks['Data'] = datetime.now().date()
if 'Zakres prac' not in df_tasks.columns:
  df_tasks['Zakres prac'] = ""
if 'Godziny' not in df_tasks.columns:
  df_tasks['Godziny'] = 0.0
if 'Stawka' not in df_tasks.columns:
  df_tasks['Stawka'] = default_rate
else:
  df_tasks['Stawka'] = df_tasks['Stawka'].fillna(default_rate)
  df_tasks['Stawka'] = df_tasks['Stawka'].replace(0, default_rate)

edited_df = st.data_editor(
    df_tasks,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "Data": st.column_config.DateColumn("Data wykonania", format="YYYY-MM-DD", required=True),
        "Zakres prac": st.column_config.TextColumn("Zakres / Opis wykonanych prac", required=True, width="large"),
        "Godziny": st.column_config.NumberColumn("Ilość godzin", min_value=0.0, format="%.2f h", step=0.5),
        "Stawka": st.column_config.NumberColumn("Stawka (PLN)", min_value=0.0, format="%.2f zł", step=5.0),
    },
)

for i, row in edited_df.iterrows():
  if pd.isna(row['Data']):
    edited_df.at[i, 'Data'] = datetime.now().date()
  elif isinstance(row['Data'], str):
    try:
      edited_df.at[i, 'Data'] = datetime.strptime(row['Data'], "%Y-%m-%d").date()
    except:
      edited_df.at[i, 'Data'] = datetime.now().date()

  if pd.isna(row['Godziny']) or row['Godziny'] == "":
    edited_df.at[i, 'Godziny'] = 0.0

  if pd.isna(row['Stawka']) or row['Stawka'] == "" or row['Stawka'] == 0:
    edited_df.at[i, 'Stawka'] = default_rate

st.session_state['tasks_list'] = edited_df.to_dict('records')

total_hours = pd.to_numeric(edited_df['Godziny'], errors='coerce').sum() if not edited_df.empty else 0.0
total_amount = (pd.to_numeric(edited_df['Godziny'], errors='coerce') * pd.to_numeric(edited_df['Stawka'], errors='coerce')).sum() if not edited_df.empty else 0.0

st.markdown("### Podsumowanie")
mcol1, mcol2 = st.columns(2)
with mcol1:
  st.metric(label="Łączna liczba godzin", value=f"{total_hours:.2f} h")
with mcol2:
  st.metric(label="Całkowita wartość robocizny", value=f"{total_amount:.2f} PLN")

st.divider()

col_btn1, col_btn2 = st.columns(2)

with col_btn1:
  if st.button("💾 Zapisz / Aktualizuj zlecenie w bazie danych", type="secondary", use_container_width=True):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    if selected_zlecenie_id is not None:
      cursor.execute(
          """UPDATE zlecenia SET project_name=?, client_name=?, address=?, order_date=?, default_rate=?, notes=? WHERE id=?""",
          (project_name, client_name, address, order_date.strftime("%Y-%m-%d"), default_rate, notes, selected_zlecenie_id),
      )
      cursor.execute("DELETE FROM pozycje_prac WHERE zlecenie_id = ?", (selected_zlecenie_id,))
      zlecenie_id = selected_zlecenie_id
    else:
      cursor.execute(
          """INSERT INTO zlecenia (project_name, client_name, address, order_date, default_rate, notes) VALUES (?, ?, ?, ?, ?, ?)""",
          (project_name, client_name, address, order_date.strftime("%Y-%m-%d"), default_rate, notes),
      )
      zlecenie_id = cursor.lastrowid

    for row in st.session_state['tasks_list']:
      if str(row['Zakres prac']).strip() != "":
        d_val = row['Data'].strftime("%Y-%m-%d") if isinstance(row['Data'], (datetime, date)) else str(row['Data'])
        r_stawka = float(row['Stawka']) if row['Stawka'] else default_rate
        r_godziny = float(row['Godziny']) if row['Godziny'] else 0.0
        cursor.execute(
            """INSERT INTO pozycje_prac (zlecenie_id, data_pracy, zakres_prac, godziny, stawka) VALUES (?, ?, ?, ?, ?)""",
            (zlecenie_id, d_val, row['Zakres prac'], r_godziny, r_stawka),
        )

    conn.commit()
    conn.close()
    st.success("Zlecenie zostało pomyślnie zapisane w bazie danych!")
    st.rerun()

with col_btn2:
  if st.button("📄 Generuj podsumowanie w formacie PDF", type="primary", use_container_width=True):
    if edited_df.empty or total_hours == 0:
      st.warning("Dodaj przynajmniej jedną pozycję prac z określoną liczbą godzin przed wygenerowaniem PDF.")
    else:
      tasks_for_pdf = []
      for row in st.session_state['tasks_list']:
        d_val = row['Data'].strftime("%Y-%m-%d") if isinstance(row['Data'], (datetime, date)) else str(row['Data'])
        r_stawka = float(row['Stawka']) if row['Stawka'] else default_rate
        r_godziny = float(row['Godziny']) if row['Godziny'] else 0.0
        tasks_for_pdf.append({
            "Data": d_val,
            "Zakres prac": row['Zakres prac'],
            "Godziny": r_godziny,
            "Stawka": r_stawka
        })

      client_data = {
          "project_name": project_name,
          "client_name": client_name,
          "address": address,
          "date": order_date,
          "notes": notes,
      }

      pdf_bytes = generate_pdf(
          client_data,
          tasks_for_pdf,
          total_hours,
          total_amount,
          default_rate,
      )

      st.success("Dokument PDF został wygenerowany pomyślnie!")
      st.download_button(
          label="📥 Pobierz kartę prac (PDF)",
          data=pdf_bytes,
          file_name=f"Ewidencja_Roboczogodzin_{project_name.replace(' ', '_')}.pdf",
          mime="application/pdf",
          use_container_width=True,
      )
