"""IPolicyConfigVista COM 声明(仅供 win_default_mic 使用)。

槽位顺序必须与系统一致 —— 少写一个方法就会错位调用到 SetEndpointVisibility
(2026-09-11 踩过:误把设备可见性改了)。Vista 变体共 11 个方法,
SetDefaultEndpoint 位于第 10 个(索引 9),没有 ResetDeviceFormat。
"""
from comtypes import GUID, COMMETHOD, IUnknown, HRESULT
from ctypes import POINTER, c_int, c_void_p, c_wchar_p, c_longlong


class IPolicyConfigVista(IUnknown):
    _iid_ = GUID("{568b9108-44bf-40b4-9006-86afe5b5a620}")
    _methods_ = (
        COMMETHOD([], HRESULT, "GetMixFormat", (["in"], c_wchar_p, "d"), (["out"], POINTER(c_void_p), "f")),
        COMMETHOD([], HRESULT, "GetDeviceFormat", (["in"], c_wchar_p, "d"), (["in"], c_int, "b"), (["out"], POINTER(c_void_p), "f")),
        COMMETHOD([], HRESULT, "SetDeviceFormat", (["in"], c_wchar_p, "d"), (["in"], c_void_p, "a"), (["in"], c_void_p, "b")),
        COMMETHOD([], HRESULT, "GetProcessingPeriod", (["in"], c_wchar_p, "d"), (["in"], c_int, "b"), (["out"], POINTER(c_longlong), "p1"), (["out"], POINTER(c_longlong), "p2")),
        COMMETHOD([], HRESULT, "SetProcessingPeriod", (["in"], c_wchar_p, "d"), (["in"], POINTER(c_longlong), "p")),
        COMMETHOD([], HRESULT, "GetShareMode", (["in"], c_wchar_p, "d"), (["out"], POINTER(c_void_p), "m")),
        COMMETHOD([], HRESULT, "SetShareMode", (["in"], c_wchar_p, "d"), (["in"], c_void_p, "m")),
        COMMETHOD([], HRESULT, "GetPropertyValue", (["in"], c_wchar_p, "d"), (["in"], c_void_p, "k"), (["out"], POINTER(c_void_p), "v")),
        COMMETHOD([], HRESULT, "SetPropertyValue", (["in"], c_wchar_p, "d"), (["in"], c_void_p, "k"), (["in"], c_void_p, "v")),
        COMMETHOD([], HRESULT, "SetDefaultEndpoint", (["in"], c_wchar_p, "d"), (["in"], c_int, "role")),
        COMMETHOD([], HRESULT, "SetEndpointVisibility", (["in"], c_wchar_p, "d"), (["in"], c_int, "visible")),
    )
