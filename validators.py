"""Расширенные валидаторы для входных данных."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from exceptions import ValidationError


@dataclass
class ValidationResult:
    """Результат валидации."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    normalized_data: Dict[str, Any]


class DataValidator:
    """Расширенный валидатор данных."""
    
    # Паттерны для валидации
    PARTNUMBER_PATTERN = re.compile(r'^[A-Za-z0-9\-_\.]+$')
    BRAND_PATTERN = re.compile(r'^[A-Za-z0-9\s\-_\.&]+$')
    
    # Известные бренды для нормализации
    BRAND_ALIASES = {
        'ti': 'Texas Instruments',
        'st': 'STMicroelectronics',
        'nxp': 'NXP',
        'infineon': 'Infineon',
        'analog': 'Analog Devices',
        'maxim': 'Maxim Integrated',
    }
    
    def __init__(self):
        self.seen_partnumbers: Set[str] = set()
    
    def validate_row(self, row: Dict[str, Any], row_index: int) -> ValidationResult:
        """Валидация одной строки данных."""
        errors = []
        warnings = []
        normalized = {}
        
        # Валидация partnumber
        partnumber = self._normalize_string(row.get("partnumber", ""))
        if not partnumber:
            errors.append("missing_partnumber")
        elif not self.PARTNUMBER_PATTERN.match(partnumber):
            warnings.append("invalid_partnumber_format")
        elif len(partnumber) > 50:
            warnings.append("partnumber_too_long")
        elif partnumber.lower() in self.seen_partnumbers:
            errors.append("duplicate_partnumber")
        else:
            self.seen_partnumbers.add(partnumber.lower())
        
        normalized["partnumber"] = partnumber
        
        # Валидация brand
        brand = self._normalize_string(row.get("brand", ""))
        if not brand:
            warnings.append("missing_brand")
        elif not self.BRAND_PATTERN.match(brand):
            warnings.append("invalid_brand_format")
        else:
            # Нормализация известных брендов
            brand_lower = brand.lower()
            if brand_lower in self.BRAND_ALIASES:
                brand = self.BRAND_ALIASES[brand_lower]
                warnings.append("brand_normalized")
        
        normalized["brand"] = brand
        
        # Валидация external_id
        external_id = self._normalize_string(row.get("external_id", ""))
        if external_id and len(external_id) > 100:
            warnings.append("external_id_too_long")
        normalized["external_id"] = external_id
        
        # Валидация gn/vn
        for field in ["gn", "vn"]:
            value = self._normalize_string(row.get(field, ""))
            if value and len(value) > 200:
                warnings.append(f"{field}_too_long")
            normalized[field] = value
        
        # Валидация числовых полей
        for field in ["quantity", "price"]:
            if field in row:
                try:
                    value = float(row[field]) if row[field] else 0.0
                    if value < 0:
                        warnings.append(f"negative_{field}")
                    normalized[field] = value
                except (ValueError, TypeError):
                    warnings.append(f"invalid_{field}_format")
                    normalized[field] = 0.0
        
        # Копируем остальные поля
        for key, value in row.items():
            if key not in normalized:
                normalized[key] = value
        
        # Добавляем метаданные
        normalized["_row_index"] = row_index
        normalized["_validation_errors"] = errors
        normalized["_validation_warnings"] = warnings
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_data=normalized
        )
    
    def _normalize_string(self, value: Any) -> str:
        """Нормализация строкового значения."""
        if value is None:
            return ""
        return str(value).strip()
    
    def validate_batch(self, rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Валидация пакета строк."""
        valid_rows = []
        invalid_rows = []
        
        for i, row in enumerate(rows):
            result = self.validate_row(row, i)
            
            if result.is_valid:
                # Добавляем предупреждения в валидные строки
                if result.warnings:
                    result.normalized_data["warnings"] = ";".join(result.warnings)
                valid_rows.append(result.normalized_data)
            else:
                # Помечаем невалидные строки
                result.normalized_data.update({
                    "status": "skip",
                    "action": "skip",
                    "reason": f"invalid_input:{result.errors[0]}",
                    "errors": ";".join(result.errors),
                    "warnings": ";".join(result.warnings) if result.warnings else "",
                })
                invalid_rows.append(result.normalized_data)
        
        return valid_rows, invalid_rows
    
    def reset(self):
        """Сброс состояния валидатора."""
        self.seen_partnumbers.clear()


class SchemaValidator:
    """Валидатор схемы данных."""
    
    REQUIRED_COLUMNS = {"partnumber"}
    OPTIONAL_COLUMNS = {"brand", "external_id", "gn", "vn", "quantity", "price", "description"}
    
    def validate_schema(self, columns: Set[str]) -> ValidationResult:
        """Валидация схемы входных данных."""
        errors = []
        warnings = []
        
        # Проверка обязательных колонок
        missing_required = self.REQUIRED_COLUMNS - columns
        if missing_required:
            errors.extend([f"missing_column_{col}" for col in missing_required])
        
        # Проверка рекомендуемых колонок
        if "brand" not in columns:
            warnings.append("missing_recommended_column_brand")
        
        # Проверка неизвестных колонок
        known_columns = self.REQUIRED_COLUMNS | self.OPTIONAL_COLUMNS
        unknown_columns = columns - known_columns
        if unknown_columns:
            warnings.extend([f"unknown_column_{col}" for col in unknown_columns])
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            normalized_data={"columns": list(columns)}
        )
