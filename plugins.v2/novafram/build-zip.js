import fs from 'fs';
import path from 'path';
import archiver from 'archiver';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 创建ZIP文件
const outputDir = path.join(__dirname, 'dist');
const zipPath = path.join(__dirname, 'novafram.zip');

// 删除旧的ZIP文件
if (fs.existsSync(zipPath)) {
  fs.unlinkSync(zipPath);
}

const output = fs.createWriteStream(zipPath);
const archive = archiver('zip', {
  zlib: { level: 9 }
});

output.on('close', () => {
  console.log(`✓ novafram.zip 已生成，大小: ${(archive.pointer() / 1024).toFixed(2)} KB`);
});

archive.on('error', (err) => {
  console.error('打包错误:', err);
  process.exit(1);
});

archive.pipe(output);

// 添加dist目录下的所有文件
archive.directory(outputDir + '/', false);

// 添加__init__.py
archive.file('__init__.py', { name: '__init__.py' });

archive.finalize();
