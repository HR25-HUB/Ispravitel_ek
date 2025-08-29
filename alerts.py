"""Система алертов для критических ошибок и мониторинга."""
from __future__ import annotations

import json
import smtplib
import time
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import requests

from logger import get_logger


class AlertLevel(Enum):
    """Уровни критичности алертов."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class Alert:
    """Структура алерта."""
    level: AlertLevel
    title: str
    message: str
    timestamp: float
    source: str
    metadata: Dict = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class AlertManager:
    """Менеджер алертов с поддержкой различных каналов уведомлений."""
    
    def __init__(self, config: Dict = None):
        self.config = config or {}
        self.log = get_logger("alerts")
        self.alerts_history: List[Alert] = []
        self.max_history = self.config.get("max_history", 1000)
        
        # Настройки для предотвращения спама
        self.cooldown_seconds = self.config.get("cooldown_seconds", 300)  # 5 минут
        self.last_alert_times: Dict[str, float] = {}
    
    def _should_send_alert(self, alert_key: str) -> bool:
        """Проверить, можно ли отправить алерт (защита от спама)."""
        current_time = time.time()
        last_time = self.last_alert_times.get(alert_key, 0)
        
        if current_time - last_time >= self.cooldown_seconds:
            self.last_alert_times[alert_key] = current_time
            return True
        
        return False
    
    def send_alert(self, level: AlertLevel, title: str, message: str, source: str = "bot_ispravitel", metadata: Dict = None) -> bool:
        """Отправить алерт."""
        alert = Alert(
            level=level,
            title=title,
            message=message,
            timestamp=time.time(),
            source=source,
            metadata=metadata or {}
        )
        
        # Добавляем в историю
        self.alerts_history.append(alert)
        if len(self.alerts_history) > self.max_history:
            self.alerts_history.pop(0)
        
        # Создаем ключ для проверки кулдауна
        alert_key = f"{level.value}:{title}"
        
        if not self._should_send_alert(alert_key):
            self.log.debug("[alerts] Alert suppressed due to cooldown: %s", title)
            return False
        
        self.log.info("[alerts] Sending %s alert: %s", level.value.upper(), title)
        
        success = True
        
        # Отправляем через все настроенные каналы
        if self.config.get("email_enabled", False):
            success &= self._send_email_alert(alert)
        
        if self.config.get("webhook_enabled", False):
            success &= self._send_webhook_alert(alert)
        
        if self.config.get("file_enabled", True):
            success &= self._write_file_alert(alert)
        
        return success
    
    def _send_email_alert(self, alert: Alert) -> bool:
        """Отправить алерт по email."""
        try:
            smtp_config = self.config.get("email", {})
            
            msg = MIMEMultipart()
            msg['From'] = smtp_config.get("from_email")
            msg['To'] = ", ".join(smtp_config.get("to_emails", []))
            msg['Subject'] = f"[{alert.level.value.upper()}] {alert.title}"
            
            body = f"""
Уровень: {alert.level.value.upper()}
Источник: {alert.source}
Время: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(alert.timestamp))}

Сообщение:
{alert.message}

Метаданные:
{json.dumps(alert.metadata, indent=2, ensure_ascii=False)}
"""
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            server = smtplib.SMTP(smtp_config.get("smtp_server"), smtp_config.get("smtp_port", 587))
            server.starttls()
            server.login(smtp_config.get("username"), smtp_config.get("password"))
            server.send_message(msg)
            server.quit()
            
            self.log.info("[alerts] Email alert sent successfully")
            return True
            
        except Exception as e:
            self.log.error("[alerts] Failed to send email alert: %s", e)
            return False
    
    def _send_webhook_alert(self, alert: Alert) -> bool:
        """Отправить алерт через webhook."""
        try:
            webhook_config = self.config.get("webhook", {})
            url = webhook_config.get("url")
            
            if not url:
                return False
            
            payload = {
                "level": alert.level.value,
                "title": alert.title,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "source": alert.source,
                "metadata": alert.metadata
            }
            
            headers = webhook_config.get("headers", {"Content-Type": "application/json"})
            timeout = webhook_config.get("timeout", 10)
            
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            response.raise_for_status()
            
            self.log.info("[alerts] Webhook alert sent successfully")
            return True
            
        except Exception as e:
            self.log.error("[alerts] Failed to send webhook alert: %s", e)
            return False
    
    def _write_file_alert(self, alert: Alert) -> bool:
        """Записать алерт в файл."""
        try:
            alerts_dir = Path(self.config.get("file_path", "logs/alerts"))
            alerts_dir.mkdir(parents=True, exist_ok=True)
            
            # Создаем файл по дате
            date_str = time.strftime('%Y-%m-%d', time.localtime(alert.timestamp))
            alert_file = alerts_dir / f"alerts_{date_str}.jsonl"
            
            alert_data = {
                "level": alert.level.value,
                "title": alert.title,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "source": alert.source,
                "metadata": alert.metadata
            }
            
            with open(alert_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(alert_data, ensure_ascii=False) + '\n')
            
            return True
            
        except Exception as e:
            self.log.error("[alerts] Failed to write file alert: %s", e)
            return False
    
    def get_recent_alerts(self, hours: int = 24, level: AlertLevel = None) -> List[Alert]:
        """Получить недавние алерты."""
        cutoff_time = time.time() - (hours * 3600)
        
        recent = [
            alert for alert in self.alerts_history
            if alert.timestamp >= cutoff_time
        ]
        
        if level:
            recent = [alert for alert in recent if alert.level == level]
        
        return sorted(recent, key=lambda a: a.timestamp, reverse=True)
    
    def get_stats(self) -> Dict:
        """Получить статистику алертов."""
        if not self.alerts_history:
            return {"total": 0}
        
        stats = {"total": len(self.alerts_history)}
        
        # Подсчет по уровням
        for level in AlertLevel:
            count = sum(1 for alert in self.alerts_history if alert.level == level)
            stats[level.value] = count
        
        # Недавние алерты (за последние 24 часа)
        recent = self.get_recent_alerts(24)
        stats["recent_24h"] = len(recent)
        
        return stats


class ProcessingAlerter:
    """Специализированный класс для алертов обработки данных."""
    
    def __init__(self, alert_manager: AlertManager):
        self.alert_manager = alert_manager
        self.log = get_logger("processing_alerter")
    
    def alert_high_error_rate(self, error_rate: float, threshold: float = 0.1, total_processed: int = 0):
        """Алерт о высоком проценте ошибок."""
        if error_rate > threshold:
            self.alert_manager.send_alert(
                level=AlertLevel.ERROR,
                title="Высокий процент ошибок обработки",
                message=f"Процент ошибок: {error_rate:.2%} (порог: {threshold:.2%}). Обработано записей: {total_processed}",
                source="processing",
                metadata={"error_rate": error_rate, "threshold": threshold, "total_processed": total_processed}
            )
    
    def alert_low_confidence(self, avg_confidence: float, threshold: float = 0.7, count: int = 0):
        """Алерт о низкой средней уверенности LLM."""
        if avg_confidence < threshold:
            self.alert_manager.send_alert(
                level=AlertLevel.WARNING,
                title="Низкая средняя уверенность LLM",
                message=f"Средняя уверенность: {avg_confidence:.3f} (порог: {threshold:.3f}). Записей: {count}",
                source="llm",
                metadata={"avg_confidence": avg_confidence, "threshold": threshold, "count": count}
            )
    
    def alert_api_failures(self, service: str, failure_count: int, threshold: int = 5):
        """Алерт о множественных сбоях API."""
        if failure_count >= threshold:
            self.alert_manager.send_alert(
                level=AlertLevel.ERROR,
                title=f"Множественные сбои API {service}",
                message=f"Количество сбоев: {failure_count} (порог: {threshold})",
                source=f"api_{service}",
                metadata={"service": service, "failure_count": failure_count, "threshold": threshold}
            )
    
    def alert_processing_time(self, processing_time: float, threshold: float = 300.0, records_count: int = 0):
        """Алерт о долгом времени обработки."""
        if processing_time > threshold:
            self.alert_manager.send_alert(
                level=AlertLevel.WARNING,
                title="Долгое время обработки",
                message=f"Время обработки: {processing_time:.1f}с (порог: {threshold:.1f}с). Записей: {records_count}",
                source="processing",
                metadata={"processing_time": processing_time, "threshold": threshold, "records_count": records_count}
            )


# Глобальный экземпляр менеджера алертов
_alert_manager: Optional[AlertManager] = None


def get_alert_manager(config: Dict = None) -> AlertManager:
    """Получить глобальный экземпляр менеджера алертов."""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager(config)
    return _alert_manager


def get_processing_alerter(config: Dict = None) -> ProcessingAlerter:
    """Получить экземпляр алертера для обработки."""
    alert_manager = get_alert_manager(config)
    return ProcessingAlerter(alert_manager)
