import re

# Fix financiero.py
with open('continuitis/financiero.py', 'r', encoding='utf-8') as f:
    fin_text = f.read()

fin_text = fin_text.replace('if bankroll_actual <= 100.0:', 'if bankroll_actual <= 40.0:')
with open('continuitis/financiero.py', 'w', encoding='utf-8') as f:
    f.write(fin_text)

# Fix HFT_GALO.py
with open('orquestadores_principales/HFT_GALO.py', 'r', encoding='utf-8') as f:
    galo_text = f.read()

galo_text = galo_text.replace('if bankroll_actual > 100.0:', 'if bankroll_actual > 40.0:')
galo_text = galo_text.replace('Bankroll cayo a {bankroll_actual:.2f} MXN (<= 100 MXN)', 'Bankroll cayo a {bankroll_actual:.2f} MXN (<= 40 MXN)')

with open('orquestadores_principales/HFT_GALO.py', 'w', encoding='utf-8') as f:
    f.write(galo_text)
