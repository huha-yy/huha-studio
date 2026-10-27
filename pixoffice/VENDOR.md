# PixOffice(收编说明)

本目录是 [workbzw/pixoffice](https://github.com/workbzw/pixoffice) 的源码收编副本。

- **上游版本**:`fe799b56193a6aafe4801468cb6ab226467564b6`(2026-10-26)
- **本地改动**(相对上游):
  - `example/office-web/vite.config.ts`:注入 `crypto.randomUUID` polyfill——修复局域网 HTTP(非安全上下文)访问办公室页面白屏
- **升级方法**:克隆上游新版 → 覆盖本目录(保留上述 polyfill 补丁)→ 提交
- **运行**(服务器模式):`PORT=8767 HOST=0.0.0.0 npm run dev -- --host 0.0.0.0`
- 许可:MIT(上游);内置美术素材商用需另行确认,见上游 README
