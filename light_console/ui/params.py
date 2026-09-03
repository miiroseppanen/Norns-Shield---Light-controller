"""Norns-style parameters. Values live on AppState — params do not copy them."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from light_console.controls.encoders import wrap_index
from light_console.state import AppState


class Parameter(ABC):
    id: str
    name: str

    @property
    @abstractmethod
    def type_name(self) -> str:
        ...

    @abstractmethod
    def get(self) -> Any:
        ...

    @abstractmethod
    def formatted(self) -> str:
        ...

    def delta(self, d: int) -> None:
        """E3: change value. Default no-op."""
        del d

    def trigger(self) -> None:
        """K3: action/enter when the type needs it."""
        return


class NumberParameter(Parameter):
    type_name = "number"

    def __init__(
        self,
        id: str,
        name: str,
        getter: Callable[[], int],
        setter: Callable[[int], None],
        minimum: int,
        maximum: int,
        step: int = 1,
        formatter: Callable[[int], str] | None = None,
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self._get = getter
        self._set = setter
        self.min = minimum
        self.max = maximum
        self.step = step
        self._formatter = formatter or str
        self._on_change = on_change

    def get(self) -> int:
        return self._get()

    def formatted(self) -> str:
        return self._formatter(self.get())

    def delta(self, d: int) -> None:
        nxt = self.get() + d * self.step
        nxt = max(self.min, min(self.max, nxt))
        if nxt != self.get():
            self._set(nxt)
            if self._on_change:
                self._on_change()


class OptionParameter(Parameter):
    type_name = "option"

    def __init__(
        self,
        id: str,
        name: str,
        getter: Callable[[], str],
        setter: Callable[[str], None],
        options: Callable[[], Sequence[str]] | Sequence[str],
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self._get = getter
        self._set = setter
        self._options = options
        self._on_change = on_change

    def options(self) -> tuple[str, ...]:
        raw = self._options() if callable(self._options) else self._options
        return tuple(raw)

    def get(self) -> str:
        return self._get()

    def formatted(self) -> str:
        return str(self.get())

    def delta(self, d: int) -> None:
        opts = self.options()
        if not opts:
            return
        try:
            idx = opts.index(self.get())
        except ValueError:
            idx = 0
        nxt = opts[wrap_index(idx, d, len(opts))]
        if nxt != self.get():
            self._set(nxt)
            if self._on_change:
                self._on_change()

    def trigger(self) -> None:
        if self._on_change:
            self._on_change()

    def set(self, value: str) -> None:
        if value != self.get():
            self._set(value)
            if self._on_change:
                self._on_change()


class ToggleParameter(Parameter):
    type_name = "toggle"

    def __init__(
        self,
        id: str,
        name: str,
        getter: Callable[[], bool],
        setter: Callable[[bool], None],
        on_change: Callable[[], None] | None = None,
    ) -> None:
        self.id = id
        self.name = name
        self._get = getter
        self._set = setter
        self._on_change = on_change

    def get(self) -> bool:
        return bool(self._get())

    def formatted(self) -> str:
        return "On" if self.get() else "Off"

    def delta(self, d: int) -> None:
        if d > 0:
            self._apply(True)
        elif d < 0:
            self._apply(False)

    def trigger(self) -> None:
        self._apply(not self.get())

    def _apply(self, value: bool) -> None:
        if value != self.get():
            self._set(value)
            if self._on_change:
                self._on_change()


class ActionParameter(Parameter):
    type_name = "action"

    def __init__(
        self,
        id: str,
        name: str,
        action: Callable[[], None],
        label: str = "K3",
    ) -> None:
        self.id = id
        self.name = name
        self._action = action
        self._label = label

    def get(self) -> None:
        return None

    def formatted(self) -> str:
        return self._label

    def trigger(self) -> None:
        self._action()


class Params:
    """Ordered parameter set. PLAY and PARAMS share these objects."""

    def __init__(self, items: Sequence[Parameter]) -> None:
        self._items = list(items)
        self._by_id = {p.id: p for p in self._items}
        self.index = 0

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, key: str | int) -> Parameter:
        if isinstance(key, int):
            return self._items[key]
        return self._by_id[key]

    @property
    def selected(self) -> Parameter:
        if not self._items:
            raise IndexError("no parameters")
        return self._items[self.index % len(self._items)]

    def select_delta(self, d: int) -> None:
        if not self._items:
            return
        self.index = wrap_index(self.index, d, len(self._items))

    def sync_index_to_state(self, state: AppState) -> None:
        if self._items:
            self.index = state.param_index % len(self._items)
            state.param_index = self.index
            state.param_count = len(self._items)

    def store_index(self, state: AppState) -> None:
        state.param_index = self.index
        state.param_count = len(self._items)


def bind_console_params(state: AppState) -> Params:
    """Master/speed/blackout/scene — one object each, used by PLAY and PARAMS."""

    def set_scene(name: str) -> None:
        state.current_scene = name
        if name in state.scenes:
            state.scene_index = state.scenes.index(name)
            state.selected_index = state.scene_index

    return Params(
        (
            NumberParameter(
                "master",
                "Master",
                getter=lambda: state.master,
                setter=lambda v: setattr(state, "master", v),
                minimum=0,
                maximum=100,
                step=1,
                formatter=lambda v: f"{v}%",
            ),
            NumberParameter(
                "speed",
                "Speed",
                getter=lambda: state.speed,
                setter=lambda v: setattr(state, "speed", v),
                minimum=20,
                maximum=240,
                step=1,
            ),
            ToggleParameter(
                "blackout",
                "Blackout",
                getter=lambda: state.blackout,
                setter=lambda v: setattr(state, "blackout", v),
            ),
            OptionParameter(
                "scene",
                "Scene",
                getter=lambda: state.current_scene,
                setter=set_scene,
                options=lambda: state.scenes,
            ),
        )
    )
