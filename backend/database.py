import sqlite3
import csv
import os

# ШАГ 1: Создаём (или открываем) файл базы данных

DB_FILE = "hackathon.db"

# Подключаемся к базе данных
conn = sqlite3.connect(DB_FILE)
cursor = conn.cursor()

print("✅ Подключились к базе данных")

# ШАГ 2: Создаём таблицы 

# Таблица КОМПАНИЙ (юрлица)
cursor.execute("""
CREATE TABLE IF NOT EXISTS companies (
    SYNTHETIC_U TEXT PRIMARY KEY,
    ORG_TYPE TEXT,
    OKFS_NAME TEXT,
    COMPANY_AGE_YEARS_GRADATION TEXT,
    ECO_MARK_LABEL TEXT,
    MAINOKVED_CODE TEXT,
    MAINOKVED_NAME TEXT,
    NEGATIVEMARK TEXT,
    AMOUNT_WORKERS_FNS_GRADATION TEXT,
    AMOUNT_WORKERS_SPARK_GRADATION TEXT,
    CL_TYPE TEXT,
    CL_PRODUCT_RKO_MARK TEXT,
    CL_PRODUCT_GAR_MARK TEXT,
    CL_PRODUCT_LOA_MARK TEXT,
    CL_PRODUCT_LEA_MARK TEXT,
    CL_PRODUCT_DEP_MARK TEXT,
    CL_PRODUCT_ZPP_MARK TEXT,
    FTS_FLAG TEXT,
    FTS_COUNTRY_NAME TEXT,
    FACTORING_MARK TEXT,
    REVENUE_COMPANY TEXT,
    GROUP_ID TEXT,
    CITY TEXT,
    REGION TEXT
);
""")
print("✅ Таблица 'companies' создана (или уже существовала)")

# Таблица ФИЗЛИЦ (связи с компаниями)
cursor.execute("""
CREATE TABLE IF NOT EXISTS persons (
    SYNTHETIC_F TEXT,
    CITY_NAME TEXT,
    RC_NAME TEXT,
    SYNTHETIC_U TEXT,
    FOREIGN KEY (SYNTHETIC_U) REFERENCES companies(SYNTHETIC_U)
);
""")
print("✅ Таблица 'persons' создана (или уже существовала)")

# Таблица ПЛАТЕЖЕЙ 
cursor.execute("""
CREATE TABLE IF NOT EXISTS payments (
    BENEFICIARY TEXT,
    PAYER TEXT,
    PAY_AMT REAL,
    PAY_CNT INTEGER,
    FOREIGN KEY (BENEFICIARY) REFERENCES companies(SYNTHETIC_U),
    FOREIGN KEY (PAYER) REFERENCES companies(SYNTHETIC_U)
);
""")
print("✅ Таблица 'payments' создана (или уже существовала)")

# ШАГ 3: Загружаем данные из CSV в таблицы
def load_csv_to_table(cursor, table_name, csv_file, expected_columns):
    """
    Загружает CSV-файл в таблицу.
    
    Параметры:
        cursor — курсор базы данных
        table_name — имя таблицы куда загружаем
        csv_file — путь к CSV файлу
        expected_columns — список колонок которые мы ожидаем
    """
    if not os.path.exists(csv_file):
        print(f"⚠️ Файл '{csv_file}' не найден, пропускаем")
        return 0
    
    count = 0
    with open(csv_file, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter=';')
        
        for row in reader:
            try:
                if table_name == 'companies':
                    cursor.execute("""
                        INSERT OR IGNORE INTO companies VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?
                        )
                    """, (
                        row.get('SYNTHETIC_U', ''),
                        row.get('ORG_TYPE', ''),
                        row.get('OKFS_NAME', ''),
                        row.get('COMPANY_AGE_YEARS_GRADATION', ''),
                        row.get('ECO_MARK_LABEL', ''),
                        row.get('MAINOKVED_CODE', ''),
                        row.get('MAINOKVED_NAME', ''),
                        row.get('NEGATIVEMARK', ''),
                        row.get('AMOUNT_WORKERS_FNS_GRADATION', ''),
                        row.get('AMOUNT_WORKERS_SPARK_GRADATION', ''),
                        row.get('CL_TYPE', ''),
                        row.get('CL_PRODUCT_RKO_MARK', ''),
                        row.get('CL_PRODUCT_GAR_MARK', ''),
                        row.get('CL_PRODUCT_LOA_MARK', ''),
                        row.get('CL_PRODUCT_LEA_MARK', ''),
                        row.get('CL_PRODUCT_DEP_MARK', ''),
                        row.get('CL_PRODUCT_ZPP_MARK', ''),
                        row.get('FTS_FLAG', ''),
                        row.get('FTS_COUNTRY_NAME', ''),
                        row.get('FACTORING_MARK', ''),
                        row.get('REVENUE_COMPANY', ''),
                        row.get('GROUP_ID', ''),
                        row.get('CITY', ''),
                        row.get('REGION', '')
                    ))
                elif table_name == 'persons':
                    cursor.execute("""
                        INSERT INTO persons VALUES (?, ?, ?, ?)
                    """, (
                        row.get('SYNTHETIC_F', ''),
                        row.get('CITY_NAME', ''),
                        row.get('RC_NAME', ''),
                        row.get('SYNTHETIC_U', '')
                    ))
                elif table_name == 'payments':
                    cursor.execute("""
                        INSERT INTO payments VALUES (?, ?, ?, ?)
                    """, (
                        row.get('BENEFICIARY', ''),
                        row.get('PAYER', ''),
                        float(row.get('PAY_AMT', 0) or 0),
                        int(row.get('PAY_CNT', 0) or 0)
                    ))
                count += 1
            except Exception as e:
                pass
    
    return count

# Загружаем каждый файл
print("\n Загружаем данные...")

n1 = load_csv_to_table(cursor, 'companies', 'df_Uid_data_hack.csv', [])
print(f"   → Загружено компаний: {n1}")

n2 = load_csv_to_table(cursor, 'persons', 'df_Fid_Uid_link_hack.csv', [])
print(f"   → Загружено физлиц: {n2}")

n3 = load_csv_to_table(cursor, 'payments', 'df_Uid_payment_hack.csv', [])
print(f"   → Загружено платежей: {n3}")


# ШАГ 4: Сохраняем изменения и закрываем соединение
conn.commit()  
conn.close()   

print(f"\n Готово! База данных сохранена в файл '{DB_FILE}'")
print(f"   Компаний: {n1}")
print(f"   Физлиц:   {n2}")
print(f"   Платежей: {n3}")