# -*- coding: utf-8 -*-
import asyncio
from pathlib import Path

from playwright.async_api import async_playwright, Playwright

from conf import LOCAL_CHROME_PATH
from utils.log import tiktok_logger


class YouTubeVideoUploader:

    def __init__(
        self,
        title: str,
        description: str,
        file_path: str,
        account_file: str,
        is_public: bool = True
    ):
        self.title = title
        self.description = description
        self.file_path = file_path
        self.account_file = account_file
        self.is_public = is_public

        self.executable_path = LOCAL_CHROME_PATH
        self.headless = False  # ⚠️ YouTube 强烈建议 False

    # -----------------------------
    # 主入口
    # -----------------------------
    async def upload(self, playwright: Playwright):
        browser = await playwright.chromium.launch(
            headless=self.headless,
            executable_path=self.executable_path,
        )

        context = await browser.new_context(
            storage_state=self.account_file
        )
        page = await context.new_page()

        await self.open_upload_dialog(page)
        await self.upload_video_file(page)
        await self.fill_title_description(page)
        await self.click_next_steps(page)
        await self.set_visibility_and_publish(page)

        # 保存 cookie（防失效）
        await context.storage_state(path=self.account_file)

        tiktok_logger.success("[YouTube] video upload finished")

        await asyncio.sleep(3)
        await context.close()
        await browser.close()

    # -----------------------------
    # Step 1: 打开上传弹窗
    # -----------------------------
    async def open_upload_dialog(self, page):
        tiktok_logger.info("[YouTube] opening upload dialog")

        await page.goto("https://www.youtube.com")
        await page.wait_for_load_state("domcontentloaded")

        await page.wait_for_selector('button[aria-label="创建"]')
        await page.click('button[aria-label="创建"]')

        await page.click('text=上传视频')

    # -----------------------------
    # Step 2: 上传视频文件
    # -----------------------------
    async def upload_video_file(self, page):
        tiktok_logger.info("[YouTube] uploading video file")

        video_path = str(Path(self.file_path).expanduser().resolve())

        # 1️⃣ 等“选择文件”阶段真正可见的组件
        file_picker = page.locator('ytcp-uploads-file-picker').first
        await file_picker.wait_for(state="visible", timeout=20000)

        # 2️⃣ 只在 file-picker 内找真正的 file input
        file_input = file_picker.locator(
            'input[type="file"][name="Filedata"]'
        )

        await file_input.wait_for(state="attached", timeout=10000)

        # 3️⃣ 注入文件（这一步才是真正触发上传）
        await file_input.set_input_files(video_path)

        tiktok_logger.success("[YouTube] video file injected, upload started")

    # -----------------------------
    # Step 3: 填标题 & 描述
    # -----------------------------
    async def fill_title_description(self, page):
        tiktok_logger.info("[YouTube] filling title & description")

        title_input = page.locator(
            'textarea#textbox[aria-label="添加标题"]'
        )
        await title_input.wait_for()
        await title_input.fill(self.title)

        desc_input = page.locator(
            'textarea#textbox[aria-label="添加说明"]'
        )
        await desc_input.fill(self.description)

        await asyncio.sleep(1)

    # -----------------------------
    # Step 4: 连续点击「下一步」
    # -----------------------------
    async def click_next_steps(self, page):
        tiktok_logger.info("[YouTube] clicking next steps")

        for i in range(3):
            next_btn = page.locator('button:has-text("下一步")')
            await next_btn.wait_for()
            await next_btn.click()
            await asyncio.sleep(1.5)

    # -----------------------------
    # Step 5: 设置可见性并发布
    # -----------------------------
    async def set_visibility_and_publish(self, page):
        tiktok_logger.info("[YouTube] setting visibility")

        if self.is_public:
            await page.click(
                'tp-yt-paper-radio-button[name="PUBLIC"]'
            )
        else:
            await page.click(
                'tp-yt-paper-radio-button[name="UNLISTED"]'
            )

        await asyncio.sleep(1)

        publish_btn = page.locator('button:has-text("发布")')
        await publish_btn.wait_for()
        await publish_btn.click()

    # -----------------------------
    # 运行入口
    # -----------------------------
    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)

    async def handle_audience_and_continue(self, page):
        tiktok_logger.info("[YouTube] setting audience: not for kids")

        not_for_kids = page.locator(
            'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]'
        )
        await not_for_kids.wait_for(state="visible", timeout=10000)
        await not_for_kids.click(force=True)

        await asyncio.sleep(0.5)

        continue_btn = page.locator(
            'ytcp-button-shape button[aria-label="继续"]'
        )
        await continue_btn.wait_for(state="visible", timeout=10000)
        await continue_btn.click(force=True)

        tiktok_logger.success("[YouTube] audience set & continued")

    # -----------------------------
    # 🔍 测试：是否能正常打开并点击上传入口
    # -----------------------------
    async def test_open_upload_only(self, playwright: Playwright):
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir="./chrome-profile-youtube",
            executable_path=self.executable_path,
            headless=False,
            slow_mo=200,
            args=[
                "--disable-blink-features=AutomationControlled",
            ]
        )

        page = await context.new_page()
        await page.goto("https://www.youtube.com")
        await page.wait_for_load_state("networkidle")

        # 1️⃣ 确认已登录
        if await page.locator('text=登录, text=Sign in').count():
            raise RuntimeError("YouTube is not logged in")

        # 2️⃣ 点击「创建」
        create_btn = page.locator(
            'yt-button-shape button[aria-label="创建"], '
            'yt-button-shape button[aria-label="Create"]'
        )
        await create_btn.wait_for(state="visible", timeout=15000)
        await create_btn.click()

        # 3️⃣ 点击「上传视频」
        upload_link = page.locator('a[href="/upload"]')
        await upload_link.wait_for(state="visible", timeout=5000)
        await upload_link.click()
        await self.upload_video_file(page)
        await self.handle_audience_and_continue(page)
        await asyncio.Event().wait()
        # await self.click_continue_until_gone(page)
        # await self.wait_until_done(page)


    async def wait_until_done(self, page, timeout=3000):
        async def wait_publish():
            await page.wait_for_selector(
                'text=公开视频已发布, text=Video published',
                timeout=timeout * 1000
            )

        async def wait_close():
            closed = asyncio.Event()
            page.on("close", lambda: closed.set())
            await closed.wait()

        done, pending = await asyncio.wait(
            [
                asyncio.create_task(wait_publish()),
                asyncio.create_task(wait_close()),
            ],
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        if not done:
            raise TimeoutError("[YouTube] wait timeout")

        tiktok_logger.success("[YouTube] upload flow finished")

    async def click_continue_until_gone(self, page, max_rounds: int = 5):
        """
        通用推进器：
        只要页面存在「继续」按钮，就一直点
        直到进入下一个大步骤（如 Visibility）
        """

        tiktok_logger.info("[YouTube] auto clicking continue buttons")

        for i in range(max_rounds):
            next_btn = page.locator('ytcp-button#next-button')

            # 如果这一轮已经没有 next-button，说明流程推进完了
            if await next_btn.count() == 0:
                tiktok_logger.info("[YouTube] no more continue button")
                return

            try:
                await next_btn.wait_for(state="visible", timeout=5000)

                # 有些时候会短暂 disabled，等它可点
                await page.wait_for_function(
                    """() => {
                        const btn = document.querySelector('ytcp-button#next-button button');
                        return btn && !btn.hasAttribute('aria-disabled');
                    }""",
                    timeout=10000
                )

                tiktok_logger.info(f"[YouTube] click continue ({i + 1})")
                await next_btn.click(force=True)

                # 给 YouTube 内部 step 动画时间
                await asyncio.sleep(1.5)

            except Exception:
                # 如果这一轮没点成功，直接 break，避免死循环
                tiktok_logger.info("[YouTube] continue button not clickable anymore")
                return

    async def continue_after_checks(self, page):
        tiktok_logger.info("[YouTube] checks → continue")

        next_btn = page.locator(
            'ytcp-button#next-button'
        )

        await next_btn.wait_for(state="visible", timeout=20000)
        await next_btn.click(force=True)

        # 给 UI 一个动画时间
        await asyncio.sleep(1)

    async def click_continue_after_checks(self, page):
        tiktok_logger.info("[YouTube] checks → continue")

        continue_btn = page.locator(
            'ytcp-button-shape button[aria-label="继续"],'
            'ytcp-button-shape button[aria-label="Next"]'
        )
        await continue_btn.wait_for(state="visible", timeout=20000)
        await continue_btn.click(force=True)

    # =============================
    # 可见性 + 发布
    # =============================
    async def set_visibility_and_publish(self, page):
        tiktok_logger.info("[YouTube] set visibility")

        if self.is_public:
            radio = page.locator(
                'tp-yt-paper-radio-button[name="PUBLIC"]'
            )
        else:
            radio = page.locator(
                'tp-yt-paper-radio-button[name="UNLISTED"]'
            )

        await radio.wait_for(state="visible", timeout=15000)
        await radio.click(force=True)

        publish_btn = page.locator(
            'ytcp-button-shape button[aria-label="发布"],'
            'ytcp-button-shape button[aria-label="Publish"]'
        )
        await publish_btn.wait_for(state="visible", timeout=15000)
        await publish_btn.click(force=True)

        tiktok_logger.success("[YouTube] published")

if __name__ == "__main__":
    uploader = YouTubeVideoUploader(
        title="test",
        description="test",
        file_path="",
        account_file="./youtube_cookie.json",
        is_public=True
    )

    async def run_test():
        async with async_playwright() as playwright:
            await uploader.test_open_upload_only(playwright)

    asyncio.run(run_test())
