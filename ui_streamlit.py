import os

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from config import load_config
from import_excel import load_excel
from logger import init_logging
from main import process_rows
from reporter import save_report

st.set_page_config(page_title="Бот Исправитель", layout="wide")

st.title("🤖 Бот Исправитель — Контроль и отчеты")

tab1, tab2 = st.tabs(["📂 Обработка", "📊 Аналитика"])

with tab1:
    uploaded_file = st.file_uploader("Загрузите Excel-файл из 1С-КА", type=["xlsx", "xls"])

    if uploaded_file:
        data = load_excel(uploaded_file)
        st.success(f"Загружено строк: {len(data)}")

        if st.button("Запустить обработку"):
            cfg = load_config()
            logger, _ = init_logging(cfg.log_level)
            with st.spinner("Обработка запущена..."):
                logger.info("[ui] start processing rows=%s", len(data))
                results = process_rows(data, cfg)
                report_path = save_report(results)
            if report_path:
                st.success("Обработка завершена!")
                logger.info("[ui] processing done, report=%s", report_path)
                # Краткая сводка по статусам
                try:
                    import collections

                    counts = collections.Counter([r.get("status", "unknown") for r in results])
                    st.write({k: counts[k] for k in sorted(counts)})
                except Exception:
                    pass
                st.download_button(
                    label="📊 Скачать отчет",
                    data=open(report_path, "rb").read(),
                    file_name=os.path.basename(report_path),
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            else:
                st.error("Не удалось сохранить отчет.")
                logger.error("[ui] failed to save report")

    st.subheader("📂 Доступные отчеты")
    reports = [f for f in os.listdir() if f.startswith("report_") and f.endswith(".xlsx")]
    if reports:
        for r in reports:
            st.write(f"- {r}")
    else:
        st.info("Пока нет сохраненных отчетов.")

with tab2:
    st.subheader("Аналитика по отчетам")
    reports = [f for f in os.listdir() if f.startswith("report_") and f.endswith(".xlsx")]
    if not reports:
        st.info("Нет отчетов для анализа")
    else:
        latest_report = sorted(reports)[-1]
        st.write(f"Используется последний отчет: {latest_report}")
        df = pd.read_excel(latest_report)

        if "status" in df.columns:
            status_counts = df["status"].value_counts()
            fig, ax = plt.subplots()
            status_counts.plot(kind="bar", ax=ax)
            ax.set_title("Статус обработки (OK/FAIL)")
            st.pyplot(fig)

        if "brand" in df.columns:
            brand_counts = df["brand"].value_counts().head(10)
            fig, ax = plt.subplots()
            brand_counts.plot(kind="barh", ax=ax)
            ax.set_title("Топ-10 брендов по количеству")
            st.pyplot(fig)

        st.dataframe(df.head(50))
