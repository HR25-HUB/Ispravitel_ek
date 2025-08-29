"""Тесты для модуля alerts."""
import json
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from alerts import Alert, AlertLevel, AlertManager, ProcessingAlerter, get_alert_manager, get_processing_alerter


class TestAlert:
    """Тесты для структуры Alert."""

    def test_alert_creation(self):
        """Тест создания алерта."""
        alert = Alert(
            level=AlertLevel.ERROR,
            title="Test Alert",
            message="Test message",
            timestamp=time.time(),
            source="test",
            metadata={"key": "value"}
        )
        
        assert alert.level == AlertLevel.ERROR
        assert alert.title == "Test Alert"
        assert alert.message == "Test message"
        assert alert.source == "test"
        assert alert.metadata == {"key": "value"}

    def test_alert_default_metadata(self):
        """Тест алерта с метаданными по умолчанию."""
        alert = Alert(
            level=AlertLevel.INFO,
            title="Test",
            message="Test",
            timestamp=time.time(),
            source="test"
        )
        
        assert alert.metadata == {}


class TestAlertManager:
    """Тесты для менеджера алертов."""

    def test_init_default(self):
        """Тест инициализации с настройками по умолчанию."""
        manager = AlertManager()
        assert manager.config == {}
        assert manager.max_history == 1000
        assert manager.cooldown_seconds == 300

    def test_init_with_config(self):
        """Тест инициализации с конфигурацией."""
        config = {
            "max_history": 500,
            "cooldown_seconds": 600,
            "file_enabled": True
        }
        manager = AlertManager(config)
        assert manager.config == config
        assert manager.max_history == 500
        assert manager.cooldown_seconds == 600

    def test_should_send_alert_first_time(self):
        """Тест отправки алерта в первый раз."""
        manager = AlertManager()
        assert manager._should_send_alert("test_key") is True

    def test_should_send_alert_cooldown(self):
        """Тест кулдауна алертов."""
        manager = AlertManager({"cooldown_seconds": 1})
        
        # Первый алерт
        assert manager._should_send_alert("test_key") is True
        
        # Сразу же второй - должен быть заблокирован
        assert manager._should_send_alert("test_key") is False
        
        # После кулдауна - должен пройти
        time.sleep(1.1)
        assert manager._should_send_alert("test_key") is True

    def test_send_alert_adds_to_history(self):
        """Тест добавления алерта в историю."""
        manager = AlertManager({"file_enabled": False})
        
        result = manager.send_alert(
            AlertLevel.WARNING,
            "Test Alert",
            "Test message",
            "test_source"
        )
        
        assert result is True
        assert len(manager.alerts_history) == 1
        
        alert = manager.alerts_history[0]
        assert alert.level == AlertLevel.WARNING
        assert alert.title == "Test Alert"
        assert alert.source == "test_source"

    def test_history_limit(self):
        """Тест ограничения размера истории."""
        manager = AlertManager({"max_history": 2, "file_enabled": False, "cooldown_seconds": 0})
        
        for i in range(3):
            manager.send_alert(AlertLevel.INFO, f"Alert {i}", "Message", "test")
        
        assert len(manager.alerts_history) == 2
        # Должны остаться последние 2 алерта
        assert manager.alerts_history[0].title == "Alert 1"
        assert manager.alerts_history[1].title == "Alert 2"

    def test_write_file_alert(self):
        """Тест записи алерта в файл."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {"file_enabled": True, "file_path": temp_dir}
            manager = AlertManager(config)
            
            alert = Alert(
                level=AlertLevel.ERROR,
                title="Test Alert",
                message="Test message",
                timestamp=time.time(),
                source="test"
            )
            
            result = manager._write_file_alert(alert)
            assert result is True
            
            # Проверяем, что файл создан
            date_str = time.strftime('%Y-%m-%d')
            alert_file = Path(temp_dir) / f"alerts_{date_str}.jsonl"
            assert alert_file.exists()
            
            # Проверяем содержимое
            with open(alert_file, 'r', encoding='utf-8') as f:
                line = f.readline().strip()
                data = json.loads(line)
                assert data["title"] == "Test Alert"
                assert data["level"] == "error"

    @patch('smtplib.SMTP')
    def test_send_email_alert(self, mock_smtp):
        """Тест отправки email алерта."""
        config = {
            "email_enabled": True,
            "email": {
                "from_email": "test@example.com",
                "to_emails": ["admin@example.com"],
                "smtp_server": "smtp.example.com",
                "smtp_port": 587,
                "username": "user",
                "password": "pass"
            }
        }
        manager = AlertManager(config)
        
        alert = Alert(
            level=AlertLevel.CRITICAL,
            title="Critical Alert",
            message="Critical message",
            timestamp=time.time(),
            source="test"
        )
        
        # Мокаем SMTP сервер
        mock_server = MagicMock()
        mock_smtp.return_value = mock_server
        
        result = manager._send_email_alert(alert)
        assert result is True
        
        # Проверяем, что методы SMTP были вызваны
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("user", "pass")
        mock_server.send_message.assert_called_once()
        mock_server.quit.assert_called_once()

    @patch('requests.post')
    def test_send_webhook_alert(self, mock_post):
        """Тест отправки webhook алерта."""
        config = {
            "webhook_enabled": True,
            "webhook": {
                "url": "https://example.com/webhook",
                "headers": {"Authorization": "Bearer token"},
                "timeout": 10
            }
        }
        manager = AlertManager(config)
        
        alert = Alert(
            level=AlertLevel.WARNING,
            title="Webhook Alert",
            message="Webhook message",
            timestamp=time.time(),
            source="test"
        )
        
        # Мокаем успешный ответ
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = manager._send_webhook_alert(alert)
        assert result is True
        
        # Проверяем параметры запроса
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[1]["json"]["title"] == "Webhook Alert"
        assert call_args[1]["json"]["level"] == "warning"

    def test_get_recent_alerts(self):
        """Тест получения недавних алертов."""
        manager = AlertManager({"file_enabled": False, "cooldown_seconds": 0})
        
        # Добавляем алерты с разными временными метками
        current_time = time.time()
        
        # Старый алерт (25 часов назад)
        old_alert = Alert(AlertLevel.INFO, "Old", "Old message", current_time - 25*3600, "test")
        manager.alerts_history.append(old_alert)
        
        # Недавний алерт (1 час назад)
        recent_alert = Alert(AlertLevel.ERROR, "Recent", "Recent message", current_time - 3600, "test")
        manager.alerts_history.append(recent_alert)
        
        recent_alerts = manager.get_recent_alerts(hours=24)
        assert len(recent_alerts) == 1
        assert recent_alerts[0].title == "Recent"

    def test_get_recent_alerts_by_level(self):
        """Тест фильтрации недавних алертов по уровню."""
        manager = AlertManager({"file_enabled": False, "cooldown_seconds": 0})
        
        current_time = time.time()
        
        # Добавляем алерты разных уровней
        manager.alerts_history.append(Alert(AlertLevel.INFO, "Info", "Info", current_time, "test"))
        manager.alerts_history.append(Alert(AlertLevel.ERROR, "Error", "Error", current_time, "test"))
        
        error_alerts = manager.get_recent_alerts(hours=24, level=AlertLevel.ERROR)
        assert len(error_alerts) == 1
        assert error_alerts[0].level == AlertLevel.ERROR

    def test_get_stats(self):
        """Тест получения статистики алертов."""
        manager = AlertManager({"file_enabled": False, "cooldown_seconds": 0})
        
        # Добавляем алерты разных уровней
        current_time = time.time()
        manager.alerts_history.extend([
            Alert(AlertLevel.INFO, "Info1", "Info", current_time, "test"),
            Alert(AlertLevel.INFO, "Info2", "Info", current_time, "test"),
            Alert(AlertLevel.ERROR, "Error1", "Error", current_time, "test"),
            Alert(AlertLevel.CRITICAL, "Critical1", "Critical", current_time - 25*3600, "test")  # Старый
        ])
        
        stats = manager.get_stats()
        
        assert stats["total"] == 4
        assert stats["info"] == 2
        assert stats["error"] == 1
        assert stats["critical"] == 1
        assert stats["recent_24h"] == 3  # Исключая старый critical


class TestProcessingAlerter:
    """Тесты для ProcessingAlerter."""

    def test_init(self):
        """Тест инициализации."""
        manager = AlertManager()
        alerter = ProcessingAlerter(manager)
        assert alerter.alert_manager is manager

    def test_alert_high_error_rate(self):
        """Тест алерта о высоком проценте ошибок."""
        manager = AlertManager({"file_enabled": False})
        alerter = ProcessingAlerter(manager)
        
        alerter.alert_high_error_rate(0.15, threshold=0.1, total_processed=100)
        
        assert len(manager.alerts_history) == 1
        alert = manager.alerts_history[0]
        assert alert.level == AlertLevel.ERROR
        assert "Высокий процент ошибок" in alert.title
        assert "15.00%" in alert.message

    def test_alert_low_confidence(self):
        """Тест алерта о низкой уверенности."""
        manager = AlertManager({"file_enabled": False})
        alerter = ProcessingAlerter(manager)
        
        alerter.alert_low_confidence(0.6, threshold=0.7, count=50)
        
        assert len(manager.alerts_history) == 1
        alert = manager.alerts_history[0]
        assert alert.level == AlertLevel.WARNING
        assert "Низкая средняя уверенность" in alert.title

    def test_alert_api_failures(self):
        """Тест алерта о сбоях API."""
        manager = AlertManager({"file_enabled": False})
        alerter = ProcessingAlerter(manager)
        
        alerter.alert_api_failures("catalog", 10, threshold=5)
        
        assert len(manager.alerts_history) == 1
        alert = manager.alerts_history[0]
        assert alert.level == AlertLevel.ERROR
        assert "catalog" in alert.title

    def test_alert_processing_time(self):
        """Тест алерта о долгом времени обработки."""
        manager = AlertManager({"file_enabled": False})
        alerter = ProcessingAlerter(manager)
        
        alerter.alert_processing_time(400.0, threshold=300.0, records_count=1000)
        
        assert len(manager.alerts_history) == 1
        alert = manager.alerts_history[0]
        assert alert.level == AlertLevel.WARNING
        assert "Долгое время обработки" in alert.title


class TestGlobalFunctions:
    """Тесты для глобальных функций."""

    def test_get_alert_manager_singleton(self):
        """Тест синглтона менеджера алертов."""
        with patch('alerts._alert_manager', None):
            manager1 = get_alert_manager()
            manager2 = get_alert_manager()
            assert manager1 is manager2

    def test_get_processing_alerter(self):
        """Тест получения ProcessingAlerter."""
        alerter = get_processing_alerter()
        assert isinstance(alerter, ProcessingAlerter)
        assert isinstance(alerter.alert_manager, AlertManager)
