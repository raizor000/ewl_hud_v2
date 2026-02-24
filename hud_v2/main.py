import sys
import os
from PyQt6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout
)
from PyQt6.QtGui import (
    QPixmap, QFontDatabase, QFont, QPainter, QLinearGradient, 
    QColor, QBrush, QPen, QTransform, QPainterPath, QFontMetrics
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QRect, QEasingCurve, 
    QVariantAnimation, QSequentialAnimationGroup, QPoint, pyqtProperty
)

def asset_path(*parts: str) -> str:
    """
    Возвращает путь к файлу в папке assets/.
    Работает как при запуске .py-файла, 
    так и из .exe (скомпилированного PyInstaller).
    """
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller: временная папка распаковки
        base = sys._MEIPASS
    else:
        # Обычный запуск: папка рядом с main.py
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "assets", *parts)

class PlayerWidget(QWidget):
    def __init__(self, name, font, is_left, team_id="T", font_family="Arial", scale_factor=1.5):
        super().__init__()
        self.player_name = name
        self.is_left = is_left # Текущая сторона экрана
        self.team_id = team_id # T или CT (фиксировано)
        self.font_family = font_family
        self.scale_factor = scale_factor
        
        # Загружаем иконку один раз
        icon_file = "terrorist_head.png" if team_id == "T" else "counterterrorists_head.png"
        icon_path = asset_path(icon_file)
        self.icon_pixmap = None
        if os.path.exists(icon_path):
            self.icon_pixmap = QPixmap(icon_path)
        
        # Цвета команды (фиксированные)
        if team_id == "T":
            self.base_c1 = QColor(255, 170, 70, 255)
            self.base_c2 = QColor(255, 80, 80, 255)
        else:
            self.base_c1 = QColor(50, 100, 255, 255)
            self.base_c2 = QColor(100, 200, 255, 255)
            
        self.red_color = QColor(255, 0, 0, 255)       # Ярко-красный для смерти
        self.dead_color = QColor(80, 80, 80, 255)     # Серый для мертвых
        
        self.current_c1 = QColor(self.base_c1)
        self.current_c2 = QColor(self.base_c2)
        
        self.hp = 100 # Здоровье игрока
        self.kills = 0
        self.deaths = 0
        self.money = 0
        
        # Индикатор полученного урона ('damage ghost')
        self._prev_hp = 100
        self._damage_alpha = 0   # 0 = прозрачный, 255 = полностью видимый
        self._damage_fade = QVariantAnimation(self)
        self._damage_fade.setDuration(1200) # 1.2 секунды на угасание
        self._damage_fade.setStartValue(255)
        self._damage_fade.setEndValue(0)
        self._damage_fade.setEasingCurve(QEasingCurve.Type.InQuad)
        self._damage_fade.valueChanged.connect(lambda v: setattr(self, '_damage_alpha', int(v)) or self.update())
        
        self.is_dead = False
        self.anim_state = ""
        
        # Скроллинг ника
        self._scroll_offset = 0
        self.scroll_speed = 0.5 # Пикселей за тик
        self.scroll_timer = QTimer(self)
        self.scroll_timer.timeout.connect(self._update_scroll)
        self.scroll_timer.start(30) # ~33 FPS
        
        self.update_side_visuals(is_left)
        
        self.anim = QVariantAnimation(self)
        self.anim.valueChanged.connect(self._update_color_blend)
        self.anim.finished.connect(self._anim_finished)
        
        # Анимация блика (shimmer)
        self._glare_progress = -1.0
        self.glare_anim = QVariantAnimation(self)
        self.glare_anim.setDuration(4000) # Длительность пролета блика (2 секунды)
        self.glare_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self.glare_anim.setStartValue(-1.0)
        self.glare_anim.setEndValue(2.0)
        self.glare_anim.valueChanged.connect(self._update_glare)

    def _update_glare(self, t):
        self._glare_progress = float(t)
        self.update()

    def _trigger_glare(self):
        if not self.is_dead:
            self.glare_anim.start()

    def _update_scroll(self):
        self._scroll_offset -= self.scroll_speed
        self.update()

    def update_side_visuals(self, is_left):
        """Обновляет только визуальное положение и скругление"""
        self.is_left = is_left
        self.update()



    def resizeEvent(self, event):
        super().resizeEvent(event)

    def die(self):
        if self.is_dead: return
        self.is_dead = True
        self.hp = 0
        self.anim_state = "dying"
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setDuration(400)
        self.anim.start()

    def revive(self):
        if not self.is_dead: return
        self.is_dead = False
        self.hp = 100
        self.anim_state = "reviving"
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.setDuration(400)
        self.anim.start()

    def set_hp(self, val):
        """Плавное или мгновенное обновление ХП"""
        new_hp = max(0, min(100, val))
        
        # Если хп уменьшилось — запускаем damage ghost
        if new_hp < self.hp and not self.is_dead:
            self._prev_hp = self.hp  # сохраняем старое значение
            self._damage_fade.stop()
            self._damage_alpha = 255
            # Пауза 0.3с + угасание 1.2с
            QTimer.singleShot(300, self._damage_fade.start)
        
        self.hp = new_hp
        if self.hp == 0 and not self.is_dead:
            self.die()
        elif self.hp > 0 and self.is_dead:
            self.revive()
        self.update()

    def set_stats(self, k, d):
        """Обновление K/D статистики"""
        self.kills = k
        self.deaths = d
        self.update()

    def set_money(self, val):
        """Обновление суммы денег"""
        self.money = val
        self.update()

    def _anim_finished(self):
        if self.anim_state == "dying":
            self.anim_state = "to_grey"
            self.anim.setDuration(800)
            self.anim.setStartValue(0.0)
            self.anim.setEndValue(1.0)
            self.anim.start()

    def blend(self, c_start, c_end, t):
        r = c_start.red() + (c_end.red() - c_start.red()) * t
        g = c_start.green() + (c_end.green() - c_start.green()) * t
        b = c_start.blue() + (c_end.blue() - c_start.blue()) * t
        a = c_start.alpha() + (c_end.alpha() - c_start.alpha()) * t
        return QColor(int(r), int(g), int(b), int(a))

    def _update_color_blend(self, t):
        t_float = float(t)
        if self.anim_state == "dying":
            c1 = self.blend(self.base_c1, self.red_color, t_float)
            c2 = self.blend(self.base_c2, self.red_color, t_float)
        elif self.anim_state == "to_grey":
            c1 = self.blend(self.red_color, self.dead_color, t_float)
            c2 = self.blend(self.red_color, self.dead_color, t_float)
        elif self.anim_state == "reviving":
            c1 = self.blend(self.dead_color, self.base_c1, t_float)
            c2 = self.blend(self.dead_color, self.base_c2, t_float)
        else: return
            
        self.current_c1 = c1
        self.current_c2 = c2
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, self.current_c1)
        gradient.setColorAt(1.0, self.current_c2)
        painter.setBrush(QBrush(gradient))
        pen = QPen(QColor(255, 255, 255, 60))
        pen.setWidth(2)
        painter.setPen(pen)
        
        # Рисуем фигуру с выборочным скруглением
        path = QPainterPath()
        radius = 8
        w, h = self.width(), self.height()
        
        if self.is_left:
            # Левый край прилегает к экрану (0 скругления), правый край скруглен
            path.moveTo(0, 0)
            path.lineTo(w - radius, 0)
            path.arcTo(w - 2 * radius, 0, 2 * radius, 2 * radius, 90, -90)
            path.lineTo(w, h - radius)
            path.arcTo(w - 2 * radius, h - 2 * radius, 2 * radius, 2 * radius, 0, -90)
            path.lineTo(0, h)
            path.lineTo(0, 0)
        else:
            # Правый край прилегает к экрану (0 скругления), левый край скруглен
            path.moveTo(w, 0)
            path.lineTo(radius, 0)
            path.arcTo(0, 0, 2 * radius, 2 * radius, 90, 90)
            path.lineTo(0, h - radius)
            path.arcTo(0, h - 2 * radius, 2 * radius, 2 * radius, 180, 90)
            path.lineTo(w, h)
            path.lineTo(w, 0)
            
        painter.drawPath(path)
        
        # Отрисовка иконки, если она есть
        if self.icon_pixmap:
            icon_h = int(self.height() * 0.8)
            icon_w = icon_h # Квадратная иконка
            padding = (self.height() - icon_h) // 2
            
            # Масштабируем иконку
            scaled_icon = self.icon_pixmap.scaled(
                icon_w, icon_h, 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Позиция X для иконки
            # Иконка ВСЕГДА должна быть у края экрана
            if self.is_left:
                icon_x = padding
            else:
                icon_x = self.width() - icon_w - padding
            
            # Сама иконка тоже должна смотреть к центру экрана
            # Зеркалим её динамически при отрисовке в зависимости от стороны
            final_icon = scaled_icon
            if self.is_left:
                # Слева - зеркалим чтобы смотрела вправо
                final_icon = final_icon.transformed(QTransform().scale(-1, 1))
            
            painter.save()
            icon_path = QPainterPath()
            icon_radius = 6 # Немного меньше общего радиуса плашки
            icon_path.addRoundedRect(icon_x, padding, icon_w, icon_h, icon_radius, icon_radius)
            painter.setClipPath(icon_path)
            
            # Рисуем иконку
            painter.drawPixmap(icon_x, padding, final_icon)
            
            # Накладываем цветовой фильтр (красный/серый)
            if self.current_c1 != self.base_c1:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
                filter_color = QColor(self.current_c1)
                filter_color.setAlpha(190)
                painter.setBrush(filter_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(icon_x, padding, icon_w, icon_h)
            
            painter.restore()

        # Отрисовка Ника (с поддержкой скроллинга)
        # Отрисовываем только если плашка развернута (ширина больше свернутой)
        if self.width() > int(80 * self.scale_factor):
            self.draw_player_name(painter)
            
        # Отрисовка HP (Полоска здоровья + % + K/D)
        if self.hp >= 0:
            self.draw_health_bar(painter)
            
        # Отрисовка Денег (в пустом месте)
        self.draw_money(painter)

    def draw_player_name(self, painter):
        w, h = self.width(), self.height()
        # Фиксированная ширина контента из "свернутого" состояния (150 unscaled)
        visible_w = int(200 * self.scale_factor)
        
        icon_area = h # Ширина головы
        stats_area = 0 # Больше не выделяем под статистику отдельный блок, она в строке HP
        
        # Область текста ограничена шириной свернутого виджета
        text_w = visible_w - icon_area - 10
        
        if self.is_left:
            text_x = icon_area
        else:
            # Справа - текст прижат к иконке, которая у правого края свернутой области
            text_x = w - visible_w + 10
            
        if text_w <= 0: return

        painter.save()
        
        # Настройка шрифта (уменьшили размер на 2 пункта)
        font = QFont(self.font_family, int(13 * self.scale_factor), QFont.Weight.Bold)
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        
        metrics = QFontMetrics(font)
        text_full_w = metrics.horizontalAdvance(self.player_name)
        
        # Clip area
        painter.setClipRect(int(text_x), 0, int(text_w), h)
        
        from PyQt6.QtGui import QImage
        # Создаем прозрачный буфер для текста
        img = QImage(int(text_w), h, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(Qt.GlobalColor.transparent)
        
        p2 = QPainter(img)
        p2.setRenderHint(QPainter.RenderHint.Antialiasing)
        p2.setFont(font)
        p2.setPen(QColor(255, 255, 255))
        
        # Смещение текста внутри буфера (примерно центр по вертикали)
        y_pos = int(h * 0.45)
        
        # Рисуем текст в буфер (с учетом скроллинга)
        if text_full_w > text_w:
            gap = 50 
            total_step = text_full_w + gap
            p2.drawText(int(self._scroll_offset), y_pos, self.player_name)
            p2.drawText(int(self._scroll_offset + total_step), y_pos, self.player_name)
            
            if abs(self._scroll_offset) >= total_step:
                self._scroll_offset = 0
        else:
            p2.drawText(0, y_pos, self.player_name)
            
        # ЭФФЕКТ БЛИКА (Золотой shimmer на буквах)
        if self._glare_progress > -1.0 and self._glare_progress < 2.0:
            glare_width = text_w * 0.5
            center_x = text_w * self._glare_progress
            
            glare_grad = QLinearGradient(center_x - glare_width, 0, center_x + glare_width, 0)
            glare_grad.setColorAt(0.0, QColor(255, 215, 0, 0))   # Прозрачный золотой
            glare_grad.setColorAt(0.5, QColor(255, 215, 0, 220)) # Яркое золото
            glare_grad.setColorAt(1.0, QColor(255, 215, 0, 0))   # Прозрачный золотой
            
            # SourceAtop: рисовать градиент поверх существующих пикселей (букв), сохраняя их непрозрачность
            p2.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            p2.setBrush(glare_grad)
            p2.setPen(Qt.PenStyle.NoPen)
            p2.drawRect(0, 0, int(text_w), h)
            
        p2.end()
        
        # Отрисовываем готовый результат на основную плашку
        painter.drawImage(int(text_x), 0, img)

        painter.restore()



    def draw_health_bar(self, painter):
        h = self.height()
        w = self.width()
        
        # Определяем область для полоски
        # Она должна быть под ником, но если ник скрыт - под иконкой
        icon_h = int(h * 0.8)
        icon_w = icon_h
        padding = (h - icon_h) // 2
        
        # Фиксированная ширина контента из "свернутого" состояния (250 unscaled)
        visible_w = int(200 * self.scale_factor)
        icon_area = h
        
        # Ширина полоски ограничена 250px
        bar_w = visible_w - icon_area - 15
        
        if self.is_left:
            bar_x = icon_area
        else:
            # При развороте вправо иконка уезжает вправо, 
            # но бар должен оставаться «привязанным» к зоне 250px
            bar_x = w - visible_w + 10
            
        bar_h = int(5 * self.scale_factor)
        bar_y = int(h * 0.60)
        
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Фон полоски (темный полупрозрачный)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 2, 2)
        
        # 2. Активная часть полоски
        if self.hp > 0:
            fill_w = int(bar_w * (self.hp / 100.0))
            
            # Выбор цвета
            if self.hp > 80: color = QColor(0, 255, 100)
            elif self.hp > 60: color = QColor(180, 255, 0)
            elif self.hp > 40: color = QColor(255, 255, 0)
            elif self.hp > 20: color = QColor(255, 130, 0)
            else: color = QColor(255, 30, 30)
            
            # 2a. Damage ghost (тёмно-красный отрезок потерянного хп)
            if self._damage_alpha > 0 and self._prev_hp > self.hp:
                ghost_start = int(bar_w * (self.hp / 100.0))
                ghost_end   = int(bar_w * (self._prev_hp / 100.0))
                ghost_w = ghost_end - ghost_start
                if ghost_w > 0:
                    ghost_color = QColor(255, 80, 60, self._damage_alpha)
                    painter.setBrush(ghost_color)
                    painter.drawRoundedRect(bar_x + ghost_start, bar_y, ghost_w, bar_h, 2, 2)
            
            # 2b. Сам хп-бар (поверх графика урона)
            painter.setBrush(color)
            painter.drawRoundedRect(bar_x, bar_y, fill_w, bar_h, 2, 2)
            
        # 3. Текст (HP + K/D) под баром
        if self.hp > 0:
            font_hp = QFont(self.font_family, int(9 * self.scale_factor), QFont.Weight.Bold)
            painter.setFont(font_hp)
            painter.setPen(QColor(255, 255, 255, 220))
            
            # Объединенная строка: Сердце + Здоровье + K/D
            # Добавляем 4 пробела для визуального отступа ~15px
            display_text = f"❤ {int(self.hp)}    {self.kills}/{self.deaths}"
            
            painter.drawText(bar_x, bar_y + bar_h + 5, bar_w, 15, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter, display_text)
            
        painter.restore()

    def draw_money(self, painter):
        w, h = self.width(), self.height()
        # Порог, с которого начинаем показывать деньги (размер свернутого состояния)
        collapsed_w = int(200 * self.scale_factor)
        full_w = int(300 * self.scale_factor) # Соответствует 450px на экране
        
        if w <= collapsed_w: return
        
        # Вычисляем прозрачность в зависимости от того, насколько "развернут" виджет
        # Чем ближе к full_width, тем четче текст
        progress = (w - collapsed_w) / (full_w - collapsed_w)
        alpha = int(255 * progress)
        if alpha < 0: alpha = 0
        if alpha > 255: alpha = 255
        
        painter.save()
        font = QFont(self.font_family, int(15 * self.scale_factor), QFont.Weight.Bold)
        painter.setFont(font)
        
        # Цвет теперь белый с учетом плавного появления
        painter.setPen(QColor(255, 255, 255, alpha))
        
        money_text = f"{self.money}$"
        
        if self.is_left:
            # Террористы (слева) -> деньги справа
            painter.drawText(collapsed_w, 0, w - collapsed_w - 15, h, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, money_text)
        else:
            # CT (справа) -> деньги слева
            painter.drawText(15, 0, w - collapsed_w - 15, h, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, money_text)
            
        painter.restore()

class PlayerListContainer(QWidget):
    """Контейнер для списка игроков, который умеет анимировать свою высоту"""
    def __init__(self, parent, is_left, font_family, scale_factor):
        super().__init__(parent)
        self.is_left = is_left
        self.font_family = font_family
        self.scale_factor = scale_factor
        
        self.players = ["Player 1", "Player 2", "Player 3", "Player 4", "Player 5"]
        self.full_width = int(300 * scale_factor)
        self.full_height = int(300 * scale_factor)
        self.is_expanded = False
        
        self.setup_plaques()
        
        self.animation = QPropertyAnimation(self, b"geometry")
        self.animation.setDuration(800)
        self.animation.setEasingCurve(QEasingCurve.Type.OutExpo)

    def setup_plaques(self):
        self.plaques = []
        font = QFont(self.font_family, int(14 * self.scale_factor), QFont.Weight.Bold)
        team_type = "T" if self.is_left else "CT"
        player_names = ["Qwintez", "BananVovan", "yanemoderator", "ameba337", "raizor"] if self.is_left else ["spliterash", "melonhell", "petiuka", "furanixx", "vladrompus"]
        for i in range(5):
            p = PlayerWidget(player_names[i], font, self.is_left, team_type, self.font_family, self.scale_factor)
            p.setParent(self)
            self.plaques.append(p)

    def update_team_side(self, is_left):
        self.is_left = is_left
        for p in self.plaques:
            p.update_side_visuals(is_left)

    def update_layout(self):
        if self.height() < 10: return
        space = 8
        plaque_h = (self.full_height - (space * 4)) // 5
        for i, p in enumerate(self.plaques):
            p_y = i * (plaque_h + space)
            # Используем текущую ширину контейнера self.width(), а не фиксированную full_width
            # Это критично для правой команды, чтобы иконка не уезжала при сворачивании
            p.setGeometry(0, p_y, self.width(), plaque_h)
            if self.height() < p_y + plaque_h // 2: p.hide()
            else: p.show()
                
    def resizeEvent(self, event):
        self.update_layout()
        super().resizeEvent(event)

class ScoreBoardWidget(QWidget):
    """Виджет скорборда с ручной отрисовкой градиентов и разделителей"""
    def __init__(self, parent, scale_factor):
        super().__init__(parent)
        self.scale_factor = scale_factor
        
        # Размеры (базовые, будут отмасштабированы)
        self.base_w = 550 # Увеличено с 400 до 550 (+150)
        self.base_h = 70
        self.setFixedSize(int(self.base_w * scale_factor), int(self.base_h * scale_factor))
        
        # Цвета команд (копия из PlayerWidget для консистентности)
        self.t1_c1 = QColor(255, 170, 70, 255)
        self.t1_c2 = QColor(255, 80, 80, 255)
        self.t2_c1 = QColor(50, 100, 255, 255)
        self.t2_c2 = QColor(100, 200, 255, 255)
        self.grey_c = QColor(60, 60, 60, 255) # Стало чуть светлее (было 40)
        self.sep_c = QColor(20, 20, 20, 255)
        self.is_swapped = False

    def swap_mirrored(self):
        self.is_swapped = not self.is_swapped
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # 1. Создаем путь для формы с прямоугольным вырезом сверху
        path = QPainterPath()
        cutout_w = w * 0.15
        cutout_h = h * 0.4 
        radius = 12
        
        # Рисуем контур: верхняя грань БЕЗ скруглений (sharp corners)
        path.moveTo(0, 0) # Начало в верхнем левом углу
        
        # Прямоугольный вырез
        path.lineTo((w - cutout_w) / 2, 0)
        path.lineTo((w - cutout_w) / 2, cutout_h)
        path.lineTo((w + cutout_w) / 2, cutout_h)
        path.lineTo((w + cutout_w) / 2, 0)
        
        # Верхний правый угол (тоже острый)
        path.lineTo(w, 0)
        
        # Правая и нижняя грани со скруглениями
        path.lineTo(w, h - radius)
        path.arcTo(w - radius*2, h - radius*2, radius*2, radius*2, 0, -90) # Bottom-right
        path.lineTo(radius, h)
        path.arcTo(0, h - radius*2, radius*2, radius*2, 270, -90) # Bottom-left
        path.closeSubpath()

        # 2. Градиент фона - зеркалим если нужно
        grad = QLinearGradient(0, 0, w, 0)
        
        c1, c2 = (self.t1_c1, self.t1_c2) if not self.is_swapped else (self.t2_c2, self.t2_c1)
        c3, c4 = (self.t2_c1, self.t2_c2) if not self.is_swapped else (self.t1_c2, self.t1_c1)

        grad.setColorAt(0.0, c1)
        grad.setColorAt(0.25, c2)
        grad.setColorAt(0.251, self.grey_c)
        grad.setColorAt(0.749, self.grey_c)
        grad.setColorAt(0.75, c3)
        grad.setColorAt(1.0, c4)
        
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 2))
        painter.drawPath(path)

class RoundEndSplashWidget(QWidget):
    """Виджет сплеша победы в раунде с трехэтапной анимацией"""
    
    # Используем pyqtProperty для анимации позиции
    def get_pos(self): return self.pos()
    def set_pos(self, pos): self.move(pos)
    pos_prop = pyqtProperty(QPoint, fget=get_pos, fset=set_pos)

    def __init__(self, parent, winner_name, is_t, font_family, scale_factor):
        super().__init__(parent)
        self.scale_factor = scale_factor
        
        # 1. Настройка картинки
        img_file = "splash_terrorists.png" if is_t else "splash_counterterrorists.png"
        path = asset_path("round_end_splash", img_file)
        
        pixmap = QPixmap(path)
        if not pixmap.isNull():
            w = int(pixmap.width() * scale_factor)
            h = int(pixmap.height() * scale_factor)
            self.pixmap = pixmap.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        else:
            self.pixmap = QPixmap(500, 150) # Заглушка
            self.pixmap.fill(Qt.GlobalColor.transparent)
            
        self.setFixedSize(self.pixmap.size())
        
        # 2. Настройка текста
        self.lbl = QLabel(f"{winner_name} Выиграла раунд", self)
        f_size = int(22 * scale_factor)
        self.lbl.setFont(QFont(font_family, f_size, QFont.Weight.Black))
        self.lbl.setStyleSheet("color: white; border: none; background: transparent;")
        self.lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl.setGeometry(0, 0, self.width(), self.height())
        
        # 3. Анимация
        self.anim_group = QSequentialAnimationGroup(self)
        
        screen = parent.geometry()
        scoreboard_h = 70 * scale_factor # Приблизительная высота
        
        start_y = -self.height()
        mid_y = int(scoreboard_h + 80)
        glide_y = mid_y # Останавливаемся в этой точке
        end_y = screen.height()
        
        center_x = (screen.width() - self.width()) // 2
        
        # Фаза 1: Быстрый вылет сверху
        fly_in = QPropertyAnimation(self, b"pos_prop")
        fly_in.setDuration(450)
        fly_in.setStartValue(QPoint(center_x, start_y))
        fly_in.setEndValue(QPoint(center_x, mid_y))
        fly_in.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Фаза 2: Плавное скольжение
        glide = QPropertyAnimation(self, b"pos_prop")
        glide.setDuration(6000) # 3 секунды слайда
        glide.setStartValue(QPoint(center_x, mid_y))
        glide.setEndValue(QPoint(center_x, glide_y))
        glide.setEasingCurve(QEasingCurve.Type.Linear)
        
        # Фаза 3: Быстрый вылет обратно вверх
        fly_out = QPropertyAnimation(self, b"pos_prop")
        fly_out.setDuration(500)
        fly_out.setStartValue(QPoint(center_x, glide_y))
        fly_out.setEndValue(QPoint(center_x, start_y))
        fly_out.setEasingCurve(QEasingCurve.Type.InCubic)
        
        self.anim_group.addAnimation(fly_in)
        self.anim_group.addAnimation(glide)
        self.anim_group.addAnimation(fly_out)
        
        self.anim_group.finished.connect(self.deleteLater)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.pixmap)

    def start(self):
        self.show()
        self.anim_group.start()

class MapSplashWidget(QWidget):
    """Премиальный виджет анонса карты с эффектом призматического раскрытия"""
    
    def __init__(self, parent, map_id, font_family, scale_factor, duration_sec=5.0):
        super().__init__(parent)
        self.scale_factor = 1
        self.font_family = font_family
        
        # 1. Загрузка ресурсов (из папки countdown_splashscreen)
        path = asset_path("countdown_splashscreen", f"{map_id.lower()}.png")
        pixmap = QPixmap(path)
        if pixmap.isNull():
            self.pixmap = QPixmap(parent.width(), parent.height()); self.pixmap.fill(Qt.GlobalColor.transparent)
        else:
            # Растягиваем на ВСЕ окно (KeepAspectRatioByExpanding чтобы не было черных полос)
            self.pixmap = pixmap.scaled(parent.width(), parent.height(), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            
        self.setFixedSize(parent.size())
        
        # 2. Переменные для анимации
        self._mask_width = 0.0      # 0.0 to 1.0 (процент раскрытия центральной полосы)
        self._chromatic_offset = 15.0 # Пиксели смещения каналов
        self._bg_opacity = 0        # Затемнение фона
        
        # 3. Группа анимаций
        self.timeline = QVariantAnimation(self)
        self.timeline.setDuration(int(duration_sec * 1000)) 
        self.timeline.setStartValue(0.0)
        self.timeline.setEndValue(1.0)
        self.timeline.valueChanged.connect(self._on_timeline)
        self.timeline.finished.connect(self.deleteLater)
        
    def _on_timeline(self, val):
        # 0.0 - 0.15: Появление линии и раскрытие (Ignite)
        if val < 0.15:
            self._mask_width = (val / 0.15)
            self._bg_opacity = int(val / 0.15 * 180)
            self._chromatic_offset = 15.0 * (1.0 - val / 0.15)
        # 0.15 - 0.85: Удержание (Stay)
        elif val < 0.85:
            self._mask_width = 1.0
            self._bg_opacity = 180
            self._chromatic_offset = 0.0
        # 0.85 - 1.0: Закрытие (Collapse)
        else:
            self._mask_width = 1.0 - (val - 0.85) / 0.15
            self._bg_opacity = int((1.0 - (val - 0.85) / 0.15) * 180)
            
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        w, h = self.width(), self.height()
        
        # 1. Затемнение фона
        painter.fillRect(self.rect(), QColor(0, 0, 0, self._bg_opacity))
        
        if self._mask_width <= 0: return

        # 2. Вычисляем область маски (центральная полоса, раскрывающаяся в бока)
        mask_w = w * self._mask_width
        mask_rect = QRect(int((w - mask_w)/2), 0, int(mask_w), h)
        
        painter.save()
        painter.setClipRect(mask_rect)
        
        # 3. Рисуем логотип (теперь фон на весь экран)
        img_x = (w - self.pixmap.width()) // 2
        img_y = (h - self.pixmap.height()) // 2
        
        if self._chromatic_offset > 0.1:
            # Отрисовка цветовых слоев (хроматическая аберрация)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
            painter.setOpacity(0.7)
            painter.drawPixmap(img_x - int(self._chromatic_offset), img_y, self.pixmap)
            painter.setOpacity(0.7)
            painter.drawPixmap(img_x + int(self._chromatic_offset), img_y, self.pixmap)
            
        painter.setOpacity(1.0)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.drawPixmap(img_x, img_y, self.pixmap)
        
        painter.restore()
        
        # 5. Линии-границы маски (световой пульс)
        line_pen = QPen(QColor(255, 255, 255, 150), 2)
        painter.setPen(line_pen)
        painter.drawLine(mask_rect.left(), 0, mask_rect.left(), h)
        painter.drawLine(mask_rect.right(), 0, mask_rect.right(), h)

    def start(self):
        self.show()
        self.timeline.start()

class MainHUD(QWidget):
    def __init__(self):
        super().__init__()
        
        # --- Данные ---
        self.team1_name_text = "TEAM A"
        self.team2_name_text = "TEAM B"
        self.team1_score_value = "0"
        self.team2_score_value = "0"
        self.round_value = "Round 1"
        self.scale_factor = 1.5
        
        self.initUI()
        
    def load_custom_font(self):
        font_path = asset_path("fonts", "minecraft.ttf")
        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families: return families[0]
        return "Arial"

    def initUI(self):
        self.font_family = self.load_custom_font()
        
        # Окно на весь экран, прозрачное, поверх всех окон
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        
        # --- Скорборд (Верх) ---
        self.score_widget = ScoreBoardWidget(self, self.scale_factor)
        sw_w = self.score_widget.width()
        self.score_widget.move((screen.width() - sw_w) // 2, 0)
        # --- Списки игроков (Низ) ---
        self.left_list = PlayerListContainer(self, True, self.font_family, self.scale_factor)
        self.right_list = PlayerListContainer(self, False, self.font_family, self.scale_factor)
        self.setup_score_texts()
        
        # Позиции для списков
        self.margin_x = 0  # Прилепляем к краям экрана
        self.margin_y = 100 
        
        # Конечная (целевая) ширина и высота
        self.target_w = self.left_list.full_width
        self.target_h = self.left_list.full_height
        
        # Ширина в "свернутом" виде (теперь 300 unscaled_px = 300 real_px)
        # 200 * 1.5 = 300
        self.collapsed_w = int(200 * self.scale_factor)

        # Позиция по Y - фиксирована
        self.y_pos = screen.height() - self.target_h - self.margin_y
        
        # Глобальные координаты СТОРОН
        self.side_left_x_collapsed = 0
        self.side_left_x_expanded = 0
        self.side_right_x_collapsed = screen.width() - self.collapsed_w
        self.side_right_x_expanded = screen.width() - self.target_w

        # Установка НАЧАЛЬНОЙ геометрии (СВЕРНУТО ПО УМОЛЧАНИЮ)
        self.left_list.setGeometry(self.side_left_x_collapsed, self.y_pos, self.collapsed_w, self.target_h)
        self.right_list.setGeometry(self.side_right_x_collapsed, self.y_pos, self.collapsed_w, self.target_h)
        self.left_list.is_expanded = False
        self.right_list.is_expanded = False
        
        # --- Таймер Бездействия (ОТКЛЮЧЕНО ПО ПРОСЬБЕ) ---
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(5000) 
        # self.idle_timer.timeout.connect(self.hide_lists)
        # self.idle_timer.start()

        # --- Таймер Волны Бликов (каждые 15 секунд) ---
        self.wave_timer = QTimer(self)
        self.wave_timer.setInterval(15000)
        self.wave_timer.timeout.connect(self._trigger_wave)
        self.wave_timer.start()

    def _trigger_wave(self):
        """Запускает волну бликов по всем игрокам с задержкой 0.5с"""
        for i in range(5):
            # Задержка 500мс между игроками
            QTimer.singleShot(i * 500, lambda idx=i: self._start_plaque_glare(idx))

    def _start_plaque_glare(self, index):
        """Запускает блик у игрока под номером index в обоих списках"""
        if index < len(self.left_list.plaques):
            self.left_list.plaques[index]._trigger_glare()
        if index < len(self.right_list.plaques):
            self.right_list.plaques[index]._trigger_glare()

    def setup_score_texts(self):
        # Настраиваем демо-статистику для игроков
        import random
        for i, p in enumerate(self.left_list.plaques):
            p.set_stats(15 - i, 5 + i)
            p.set_money(random.randint(800, 16000))
        for i, p in enumerate(self.right_list.plaques):
            p.set_stats(12 - i, 8 + i)
            p.set_money(random.randint(800, 16000))

        base = self.score_widget
        f_name = QFont(self.font_family, int(16 * self.scale_factor), QFont.Weight.Bold)
        f_score = QFont(self.font_family, int(24 * self.scale_factor), QFont.Weight.Black)
        f_round = QFont(self.font_family, int(12 * self.scale_factor), QFont.Weight.Medium)
        
        self.lbl_t1_name = QLabel(self.team1_name_text, base); self.lbl_t1_name.setFont(f_name); self.lbl_t1_name.setStyleSheet("color: white;"); self.lbl_t1_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_t2_name = QLabel(self.team2_name_text, base); self.lbl_t2_name.setFont(f_name); self.lbl_t2_name.setStyleSheet("color: white;"); self.lbl_t2_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_t1_score = QLabel(self.team1_score_value, base); self.lbl_t1_score.setFont(f_score); self.lbl_t1_score.setStyleSheet("color: white;"); self.lbl_t1_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_t2_score = QLabel(self.team2_score_value, base); self.lbl_t2_score.setFont(f_score); self.lbl_t2_score.setStyleSheet("color: white;"); self.lbl_t2_score.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_round = QLabel(self.round_value, base); self.lbl_round.setFont(f_round); self.lbl_round.setStyleSheet("color: white;"); self.lbl_round.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        w, h = base.width(), base.height()
        cy, bw, sw = int(h * 0.5), int(w * 0.25), int(w * 0.1)
        self.lbl_t1_name.setGeometry(int(w * 0.12) - bw//2, cy - 20, bw, 40)
        self.lbl_t2_name.setGeometry(int(w * 0.88) - bw//2, cy - 20, bw, 40)
        self.lbl_t1_score.setGeometry(int(w * 0.35) - sw//2, cy - 30, sw, 60)
        self.lbl_t2_score.setGeometry(int(w * 0.65) - sw//2, cy - 30, sw, 60)
        self.lbl_round.setGeometry(int(w * 0.5) - int(w*0.4)//2, int(h * 0.8) - 15, int(w*0.4), 30)

    def show_round_end(self, winner_name, is_t):
        """Запуск сплеша победы"""
        splash = RoundEndSplashWidget(
            self, winner_name, is_t, 
            self.font_family, 1
        )
        splash.start()

    def show_map_announcement(self, map_name, duration_sec=5.0):
        """Запуск премиального анонса карты"""
        splash = MapSplashWidget(
            self, map_name,
            self.font_family, self.scale_factor,
            duration_sec=duration_sec
        )
        splash.start()

    def swap_sides(self):
        """Полная смена сторон (свап) системно и визуально"""
        # 1. Свапаем тексты
        self.team1_name_text, self.team2_name_text = self.team2_name_text, self.team1_name_text
        self.team1_score_value, self.team2_score_value = self.team2_score_value, self.team1_score_value
        self.lbl_t1_name.setText(self.team1_name_text)
        self.lbl_t2_name.setText(self.team2_name_text)
        self.lbl_t1_score.setText(self.team1_score_value)
        self.lbl_t2_score.setText(self.team2_score_value)
        
        # 2. Скорборд
        self.score_widget.swap_mirrored()
        
        # 3. Списки игроков (флаги сторон)
        self.left_list.update_team_side(not self.left_list.is_left)
        self.right_list.update_team_side(not self.right_list.is_left)
            
        # 4. Запускаем анимацию в новое состояние
        if self.left_list.is_expanded:
            self.expand()
        else:
            self.collapse()

    def expand(self):
        """Разворачивает списки игроков вручную"""
        for lst in [self.left_list, self.right_list]:
            lst.animation.stop()
            lst.animation.setStartValue(lst.geometry())
            if lst.is_left:
                lst.animation.setEndValue(QRect(self.side_left_x_expanded, self.y_pos, self.target_w, self.target_h))
            else:
                lst.animation.setEndValue(QRect(self.side_right_x_expanded, self.y_pos, self.target_w, self.target_h))
            lst.is_expanded = True
            lst.animation.start()

    def collapse(self):
        """Сворачивает списки игроков вручную"""
        for lst in [self.left_list, self.right_list]:
            lst.animation.stop()
            lst.animation.setStartValue(lst.geometry())
            if lst.is_left:
                lst.animation.setEndValue(QRect(self.side_left_x_collapsed, self.y_pos, self.collapsed_w, self.target_h))
            else:
                lst.animation.setEndValue(QRect(self.side_right_x_collapsed, self.y_pos, self.collapsed_w, self.target_h))
            lst.is_expanded = False
            lst.animation.start()

    def toggle(self):
        """Переключает состояние списков (развернут/свернут)"""
        if self.left_list.is_expanded:
            self.collapse()
        else:
            self.expand()

    def show_lists_and_reset_timer(self):
        self.expand()

    def hide_lists(self):
        self.collapse()
                
    # =========================================================================
    # === ПУБЛИЧНЫЙ API — методы для внешнего управления HUD =================
    # =========================================================================

    # --- Счёт команд ---

    def set_score(self, team: str, score: int):
        """
        Устанавливает счёт для указанной команды.
        team: 'T' — левая команда (Террористы), 'CT' — правая (КТ).
        score: число очков.
        Пример: hud.set_score('T', 5)
        """
        value = str(score)
        if team == 'T':
            self.team1_score_value = value
            self.lbl_t1_score.setText(value)
        else:
            self.team2_score_value = value
            self.lbl_t2_score.setText(value)

    # --- Название команды ---

    def set_team_name(self, team: str, name: str):
        """
        Устанавливает название команды.
        team: 'T' или 'CT'.
        name: строковое название (например 'NAVI').
        Пример: hud.set_team_name('CT', 'NAVI')
        """
        if team == 'T':
            self.team1_name_text = name
            self.lbl_t1_name.setText(name)
        else:
            self.team2_name_text = name
            self.lbl_t2_name.setText(name)

    # --- Раунд ---

    def set_round(self, round_text: str):
        """
        Устанавливает текст текущего раунда.
        round_text: произвольная строка (например 'Round 16').
        Пример: hud.set_round('Round 16')
        """
        self.round_value = round_text
        self.lbl_round.setText(round_text)

    # --- Игроки ---

    def set_player_name(self, team: str, index: int, name: str):
        """
        Меняет ник игрока.
        team: 'T' (левая) или 'CT' (правая).
        index: 0–4, порядковый номер игрока сверху вниз.
        Пример: hud.set_player_name('T', 0, 'S1mple')
        """
        lst = self.left_list if team == 'T' else self.right_list
        if 0 <= index < len(lst.plaques):
            lst.plaques[index].player_name = name
            lst.plaques[index]._scroll_offset = 0
            lst.plaques[index].update()

    def set_player_hp(self, team: str, index: int, hp: int):
        """
        Устанавливает HP игрока (0–100). При 0 — запускает анимацию смерти.
        Пример: hud.set_player_hp('CT', 2, 45)
        """
        lst = self.left_list if team == 'T' else self.right_list
        if 0 <= index < len(lst.plaques):
            lst.plaques[index].set_hp(hp)

    def set_player_stats(self, team: str, index: int, kills: int, deaths: int):
        """
        Устанавливает статистику K/D игрока.
        Пример: hud.set_player_stats('T', 1, 12, 3)
        """
        lst = self.left_list if team == 'T' else self.right_list
        if 0 <= index < len(lst.plaques):
            lst.plaques[index].set_stats(kills, deaths)

    def set_player_money(self, team: str, index: int, amount: int):
        """
        Устанавливает баланс игрока.
        Пример: hud.set_player_money('T', 0, 4300)
        """
        lst = self.left_list if team == 'T' else self.right_list
        if 0 <= index < len(lst.plaques):
            lst.plaques[index].set_money(amount)

    def kill_player(self, team: str, index: int):
        """
        Запускает анимацию смерти игрока.
        Пример: hud.kill_player('CT', 4)
        """
        lst = self.left_list if team == 'T' else self.right_list
        if 0 <= index < len(lst.plaques):
            lst.plaques[index].die()

    def revive_player(self, team: str, index: int):
        """
        Воскрешает игрока (возвращает HP 100, снимает серость).
        Пример: hud.revive_player('T', 0)
        """
        lst = self.left_list if team == 'T' else self.right_list
        if 0 <= index < len(lst.plaques):
            lst.plaques[index].revive()

    # --- Визуальные события ---

    def show_win_splash(self, winner_name: str, is_t: bool):
        """
        Показывает сплеш победы в раунде.
        winner_name: название победившей команды.
        is_t: True если победили террористы (оранжевый сплеш), False — КТ (синий).
        Пример: hud.show_win_splash('NAVI', True)
        """
        self.show_round_end(winner_name, is_t)

    # --- Устаревшие обертки (для обратной совместимости) ---
    def trigger_death(self, is_left: bool, index: int):
        """Устаревший метод. Используй kill_player('T'/'CT', index)."""
        self.kill_player('T' if is_left else 'CT', index)

    def trigger_revive(self, is_left: bool, index: int):
        """Устаревший метод. Используй revive_player('T'/'CT', index)."""
        self.revive_player('T' if is_left else 'CT', index)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("EWL Season 2 HUD v2.0")
    
    # Иконка приложения (для панели задач и заголовка окна)
    icon_path = asset_path("icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QPixmap(icon_path))
    
    hud = MainHUD()
    hud.setWindowTitle("EWL Season 2 HUD v2.0")
    hud.show()
    
    # Сценарий демо
    # 1. Списки теперь свернуты при старте (300px)
    
    # 2. Все автоматические триггеры развертки отключены.
    # Списки развернутся ТОЛЬКО если вызвать метод вручную.
    QTimer.singleShot(3000, lambda: hud.expand())
    QTimer.singleShot(10000, lambda: hud.collapse())
    
    # 3. Через 8 сек кто-то умирает -> это вызывает событие! Списки разворачиваются.
    QTimer.singleShot(8000, lambda: hud.trigger_death(True, 0)) # Слева, 0 (первый игрок)
    QTimer.singleShot(8000, lambda: hud.trigger_death(False, 2)) # Справа, 2 (третий игрок)
    
    # --- ТЕСТ СПЛЕША ---
    # На 12-й секунде показываем победу
    QTimer.singleShot(12000, lambda: hud.show_round_end("TEAM A", True))
    
    # --- ТЕСТ ХП ---
    # На 3-й секунде у первого игрока слева становится 75 HP (салатовый)
    QTimer.singleShot(3000, lambda: hud.left_list.plaques[0].set_hp(75))
    # На 5-й секунде у него же становится 45 HP (желтый)
    QTimer.singleShot(5000, lambda: hud.left_list.plaques[0].set_hp(45))
    # На 7-й секунде у него остается 15 HP (красный)
    QTimer.singleShot(7000, lambda: hud.left_list.plaques[0].set_hp(15))
    
    # На 4-й секунде у второго игрока справа становится 50 HP
    QTimer.singleShot(4000, lambda: hud.right_list.plaques[1].set_hp(50))
    # На 9-й секунде он почти умирает
    QTimer.singleShot(9000, lambda: hud.right_list.plaques[1].set_hp(5))

    # 5. Через 15 секунд они оживают -> списки опять разворачиваются.
    QTimer.singleShot(15000, lambda: hud.trigger_revive(True, 0))
    QTimer.singleShot(15000, lambda: hud.trigger_revive(False, 2))
    
    # --- ТЕСТ СВАПА ---
    # На 20-й секунде делаем свап сторон!
    QTimer.singleShot(20000, hud.swap_sides)

    #hud.expand()

    

    # --- ТЕСТ АНОНСА КАРТЫ ---
    # На 25-й секунде показываем анонс карты (например, Anubis) на 5 секунды
    # QTimer.singleShot(25000, lambda: hud.show_map_announcement("anubis", duration_sec=5.0))
    
    sys.exit(app.exec())
