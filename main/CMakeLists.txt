idf_component_register(
    SRCS "main.c"
         "ui_pixel.c"
         "ui_pixel_math.c"
         "app_state.c"
         "app_protocol.c"
         "dev_info.c"
         "app_events.c"
         "app_sound.c"
         "app_ui.c"
         "nvs_settings.c"
         "adpcm.c"
         "audio_streamer.c"
         "ble_audio.c"
         "ble_dtm.c"      # 自 ESP-IDF 5.5.3 拷入:host 层 DTM API 未编入 libbt.a
         "console_cmds.c"
         "time_sync.c"
         "mode.c"
         "usb_link.c"
         "usb_link_framing.c"
    INCLUDE_DIRS "."
    REQUIRES bsp
             json
             esp_app_format  # dev_info.c:esp_app_get_description(固件版本上报)
             esp_hw_support  # dev_info.c:esp_chip_info / esp_read_mac(芯片与 MAC)
             spi_flash       # dev_info.c:esp_flash_get_size(Flash 容量)
             nvs_flash
             console  # IDF >= 5.5: esp_console 组件已重命名为 console
             bt
             esp_pm       # 空闲 light sleep + CPU 变频(录音会话锁见 app_main)
             esp_driver_usb_serial_jtag
)
