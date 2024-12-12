import datetime
from discord.components import SelectOption
from discord.utils import MISSING
import pymysql
import random
import asyncio
import discord
import enum
from typing import List, Optional, TypedDict, Type, Union, cast
import json
from discord.ext import tasks
from discord import app_commands, Interaction, ui, ButtonStyle
import sys
import dotenv
import os

dotenv.load_dotenv()


class ContryEnum(enum.Enum):
    오키니스탄 = 1
    미세란제국 = 2
    에리칸바튼 = 3


class ManifactureInsideType(TypedDict):
    level: int
    option: str
    last_claim: datetime.datetime


class ManifactureType(TypedDict):
    town: ManifactureInsideType
    bank: ManifactureInsideType
    restraunt: ManifactureInsideType
    watertank: ManifactureInsideType
    powerstation: ManifactureInsideType


class InfoType(TypedDict):
    name: str
    contry: str
    money: int
    food: int
    water: int
    electric: int


def getJson(url: str):
    '''
    JSON 구하기
    -----------
    - url: JSON 파일 주소

    - ex) getJson('./json/util.json')

    `return 파싱된 JSON 파일`
    '''
    file = open(url, 'r', encoding="utf-8")
    data: dict = json.load(file)
    return data


Manifacture = getJson("./json/manifacture.json")


def nameToValue(name: str):
    nameDict = {
        "restraunt": "food",
        "bank": "money",
        "powerstation": "electric",
        "watertank": "water",
        "town": "town"
    }
    valueDict = {
        "food": "restraunt",
        "money": "bank",
        "electric": "powerstation",
        "water": "watertank"
    }
    if name in nameDict:
        return nameDict[name]
    elif name in valueDict:
        return valueDict[name]
    else:
        return ""


def valueToKorean(name: str):
    nameDict = {
        "restraunt": "식당",
        "bank": "은행",
        "powerstation": "발전소",
        "watertank": "물탱크",
        "town": "회관"
    }
    valueDict = {
        "food": "음식",
        "money": "돈",
        "water": "식수",
        "electric": "전기"
    }
    if name in nameDict:
        return nameDict[name]
    elif name in valueDict:
        return valueDict[name]
    else:
        return ""


def makeEmbed(embed: discord.Embed, name: list, values: tuple):
    if (len(name) != len(values)):
        return None
    for i in range(len(name)):
        embed.add_field(name=name[i], value=values[i])
    return embed


def authorize(id: int | str):
    '''없으면 True'''
    if str(id) in User._instances:
        return False
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM info WHERE id = %s", (str(id),))
    flag = cur.fetchone()
    cur.close()
    return False if flag[0] else True


def makeDictionary(keys: list, values: tuple):
    '''
    keys : values 딕셔너리 만들기
    ----------------------------
    `return {} : not keys or not values`
    `return {keys:values} dict`
    '''
    if not values or not keys:
        return {}

    return {keys[i]: values[i] for i in range(len(keys))}


class Pannel:
    _instances: dict[str, 'Pannel'] = {}

    def __new__(cls, id, message):
        if not str(id) in cls._instances:
            cls._instances[str(id)] = super().__new__(cls)
        return cls._instances[str(id)]

    def __init__(self, id: int, message: discord.Message):
        self.user = User(id)
        self.id = str(id)
        self.message = message
        self.error = ""

    async def setupMessage(self):
        embed = discord.Embed(title="메인")
        __manifacture = self.user.getManifacture()
        now = datetime.datetime.now()
        claimText = ""
        infoText = ""
        __info = self.user.getInfo()
        for i in __manifacture:
            if i == "town":
                claimText += f"{valueToKorean(i)} {__manifacture[i]['level']}레벨\n"
                continue
            last: int = int(
                (now-__manifacture[i]['last_claim']).total_seconds()/60)
            maniData = Manifacture[i][str(__manifacture[i]['level'])]
            claimText += f"{valueToKorean(i)} {__manifacture[i]['level']}레벨 (분당 {__manifacture[i]['level']} 생산)\n"
            claimText += f"{maniData['value']*last if maniData['value']*last < maniData['max'] else maniData['max']}/{maniData['max']}\n"
            infoText += f"{valueToKorean(nameToValue(i))} {int(__info[nameToValue(i)])}\n"
        embed.add_field(name="시설", value="```"+claimText+"```", inline=False)
        embed.add_field(name="자원", value="```"+infoText+"```", inline=False)
        await self.message.edit(content="", embed=embed, view=PannelSetupView(self))


def getManifactureRequire(key: str, manifacture: ManifactureType):
    current = Manifacture[key][str(manifacture[key]['level'])]
    next = Manifacture[key][str(manifacture[key]['level']+1)]
    require = current['require'].split(" ")
    data = makeDictionary(['money', 'electric', 'water', 'food'], require)
    return current, next, data


def getSatisfaction(key: str, manifacture: ManifactureType, info: InfoType):
    __, __, data = getManifactureRequire(key, manifacture)
    for i in data:
        if int(info[i]) < int(data[i]):
            return True
    return False


class UpgradePannel:
    _instances: dict[str, 'UpgradePannel'] = {}

    def __new__(cls, pannel: Pannel):
        if not str(pannel.id) in cls._instances:
            cls._instances[str(pannel.id)] = super().__new__(cls)
        return cls._instances[str(pannel.id)]

    def __init__(self, pannel: Pannel):
        self.pannel = pannel

    async def setupMessage(self):
        embed = discord.Embed(title="업그레이드")
        await self.pannel.message.edit(content="", embed=embed, view=UpgradeSetupView(self))

    async def upgradeMessage(self, interaction: Interaction):
        key = interaction.data['values'][0]
        if "back" in key:
            return await self.pannel.setupMessage()
        manifacture = self.pannel.user.getManifacture()
        info = self.pannel.user.getInfo()
        current, next, data = getManifactureRequire(key, manifacture)
        embed = discord.Embed(title=f"{valueToKorean(key)} 업그레이드")
        text = ""
        for i in data:
            text += f"{valueToKorean(i)} {info[i]}/{data[i]}\n"
        embed.add_field(name="제작재료", value="```"+text+"```", inline=False)
        if key != "town":
            embed.add_field(
                name=f"{current['value']}/m > {next['value']}/m", value="\u200b")
            embed.add_field(
                name=f"저장량 {current['max']} > 저장량 {next['max']}", value="\u200b")
        await self.pannel.message.edit(content="", embed=embed, view=UpgradeView(self, key))


class UpgradeView(ui.View):
    def __init__(self, parent: UpgradePannel, key: str):
        self.parent = parent
        self.key = key
        super().__init__(timeout=None)
        self.manifacture = self.parent.pannel.user.getManifacture()
        self.info = self.parent.pannel.user.getInfo()
        self.yes_button()

    def yes_button(self):
        button = ui.Button(label="업그레이드", style=ButtonStyle.green, disabled=getSatisfaction(
            self.key, self.manifacture, self.info))
        button.callback = self.yes_callback
        self.add_item(button)

    async def yes_callback(self, interaction: Interaction):
        await interaction.response.edit_message(content="업그레이드중이에요!", embed=None, view=None)
        __, __, data = getManifactureRequire(self.key, self.manifacture)
        self.manifacture[self.key]['level'] += 1
        for i in data:
            self.info[i] -= int(data[i])
        self.parent.pannel.user.setManifacture(self.manifacture)
        self.parent.pannel.user.setInfo(self.info)
        await self.parent.setupMessage()

    @ui.button(label="뒤로가기", style=ButtonStyle.red)
    async def no_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(content="이동중이에요!", embed=None, view=None)
        await self.parent.setupMessage()


class UpgradeSetupView(ui.View):
    def __init__(self, parent: UpgradePannel):
        self.parent = parent
        super().__init__(timeout=None)
        self.upgrade_select()

    def upgrade_select(self):
        manifacture = self.parent.pannel.user.getManifacture()
        options = [SelectOption(label="뒤로 돌아가기", value="back")]
        for key in manifacture:
            try:
                Manifacture[key][str(manifacture[key]['level']+1)]
            except KeyError:
                options.append(SelectOption(
                    label=f"{valueToKorean(key)} {manifacture[key]['level']+1}레벨 업그레이드", value=f"back{key}", description="미구현, 선택시 뒤로가기"))
            else:
                options.append(SelectOption(
                    label=f"{valueToKorean(key)} {manifacture[key]['level']+1}레벨 업그레이드", value=key))
        select = ui.Select(options=options)
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: Interaction):
        await interaction.response.edit_message(content="이동중이에요!", embed=None, view=None)
        await self.parent.upgradeMessage(interaction)


class PannelSetupView(ui.View):
    def __init__(self, parent: 'Pannel'):
        super().__init__(timeout=0)
        self.parent = parent

    @ui.button(label="징수하기", style=ButtonStyle.green, emoji="💰")
    async def claim_callback(self, interaction: Interaction, button: ui.Button):
        clicked = datetime.datetime.now()
        __manifacture = self.parent.user.getManifacture()
        output = {}
        for key in __manifacture:
            if key == "town":
                continue
            time: datetime.timedelta = clicked-__manifacture[key]["last_claim"]
            min = time.total_seconds()//60
            earn = Manifacture[str(key)][str(__manifacture[key]['level'])
                                         ]['value']*min
            maxEarn = Manifacture[str(key)][str(
                __manifacture[key]['level'])]['max']
            if earn > maxEarn:
                earn = maxEarn
            self.parent.user.getInfo()[nameToValue(
                key)] += int(earn)
            output[valueToKorean(key)] = int(earn)
            __manifacture[key]["last_claim"] = clicked
        self.parent.user.setManifacture(__manifacture)
        embed = discord.Embed(
            title="징수내역", color=interaction.user.accent_color)
        embed = makeEmbed(embed, list(output.keys()), list(output.values()))
        return await interaction.response.edit_message(content="", embed=embed, view=BackSetupView(self.parent))

    @ui.button(label="새로고침", style=ButtonStyle.gray, emoji="🔁")
    async def refresh_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(content="새로고침 중이에요!", embed=None, view=None)
        await self.parent.setupMessage()

    @ui.button(label="업그레이드", style=ButtonStyle.green, emoji="⬆", row=2)
    async def upgrade_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(content="업그레이드창으로 이동중!", view=None, embed=None)
        await UpgradePannel(self.parent).setupMessage()

    @ui.button(label="수동저장", style=ButtonStyle.green, emoji="⬇", row=2)
    async def save_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(content="저장중!")
        self.parent.user.save()
        await self.parent.message.edit(content="저장완료!")


class BackSetupView(ui.View):
    def __init__(self, parent, timeout: int = 0):
        super().__init__(timeout=timeout)
        self.parent = parent

    async def __timeout_task_impl(self):
        await self.parent.setupMessage()

    @ui.button(label="뒤로가기", style=ButtonStyle.red, emoji="⬅")
    async def back_callback(self, interaction: Interaction, button: ui.Button):
        await interaction.response.edit_message(content="뒤로 가고있습니다", embed=None, view=None)
        await self.parent.setupMessage()


class User:
    _instances: dict[str, 'User'] = {}

    def __new__(cls, id):
        if not id in cls._instances:
            cls._instances[id] = super().__new__(cls)
        return cls._instances[id]

    def __init__(self, id: int):
        self.id = str(id)
        self.error = ""
        if not hasattr(self, 'inventory'):
            self.__inventory = self.__getInventory()
        if not hasattr(self, 'manifacture'):
            self.__manifacture = self.__getManifacture()
        if not hasattr(self, 'info'):
            self.__info = self.__getInfo()

    def getAmount(self, code: int) -> int:
        return self.__inventory[code] if code in self.__inventory else 0

    def getInfo(self) -> InfoType:
        return self.__info

    def setInfo(self, value: InfoType):
        self.__info = value

    def getManifacture(self):
        return self.__manifacture

    def setManifacture(self, value: ManifactureType):
        self.__manifacture = value

    def __getInventory(self) -> dict[int, int]:
        cur = con.cursor()
        cur.execute("SELECT data FROM inventory WHERE id = %s", (self.id))
        data: tuple[str] | None = cur.fetchone()
        cur.close()
        if not data:
            self.error = "인벤토리를 찾을 수 없습니다."
            del User._instances[self.id]
            return {}
        return json.loads(data[0])

    def __getInfo(self) -> InfoType:
        cur = con.cursor()
        cur.execute(
            "SELECT name,contry,money,food,water,electric FROM info WHERE id = %s", (self.id))
        data: tuple[str, str, int, int, int, int] | None = cur.fetchone()
        cur.close()
        if not data:
            self.error = "인포를 찾을 수 없습니다."
            del User._instances[self.id]
            raise Exception("인포를 찾을 수 없습니다.")
        info = makeDictionary(
            ['name', 'contry', 'money', 'food', 'water', 'electric'], data)
        return cast(InfoType, info)

    def __del__(self):
        raise Exception(self.error)

    def __getManifacture(self) -> ManifactureType:
        cur = con.cursor()
        cur.execute(
            "SELECT name,level,option,last_claim FROM manifacture WHERE id = %s", (self.id))
        data: tuple[tuple[str, int, str, datetime.datetime]
                    ] | None = cur.fetchall()
        cur.close()
        if not data:
            self.error = "제조시설을 찾을 수 없습니다."
            del User._instances[self.id]
            raise Exception("제조시설을 찾을 수 없습니다.")
        manifacture = {}
        for row in data:
            manifacture[row[0]] = makeDictionary(
                ['level', 'option', 'last_claim'], row[1:])
        return cast(ManifactureType, manifacture)

    def getClaim(self):
        for key, value in self.__manifacture:
            print(key, value)

    def getItem(self, code: int, amount: int) -> None:
        if amount*-1 > self.getAmount(code):
            raise Exception(
                f"아이템이 부족합니다. 아이템 : {code}, 사용개수:{amount}, 보유개수:{self.getAmount(code)}")
        if code in self.__inventory:
            self.__inventory[code] += amount
        else:
            self.__inventory[code] = amount

    def InfoEmbed(self):
        data = self.__info
        embed = discord.Embed(title=f"{data['contry']} {data['money']}")
        embed1 = makeEmbed(embed, ['돈', '식량', '물', '전기'], values=(
            data["money"], data["food"], data["water"], data["electric"]))
        return embed1

    def save(self):
        cur = con.cursor()
        cur.execute("UPDATE info SET money = %s,food=%s,water=%s,electric=%s WHERE id = %s",
                    (self.__info["money"], self.__info["food"], self.__info["water"], self.__info["electric"], self.id))
        for i in self.__manifacture:
            cur.execute("UPDATE manifacture SET level=%s,option=%s,last_claim=%s WHERE id = %s AND name = %s", (
                self.__manifacture[i]["level"], self.__manifacture[i]["option"], self.__manifacture[i]["last_claim"], self.id, i))
        con.commit()
        cur.close()


KST = datetime.timezone(datetime.timedelta(hours=9))


class MyClient(discord.Client):
    async def on_ready(self):
        await self.wait_until_ready()
        await tree.sync()
        print(f"{self.user} 에 로그인하였습니다!")

    @tasks.loop(time=datetime.time(hour=0, minute=0, second=0, tzinfo=KST))
    async def saveData(self):
        for user in User._instances.values():
            user.id


intents = discord.Intents.all()
client = MyClient(intents=intents)
tree = app_commands.CommandTree(client)
con = pymysql.connect(host=os.environ['host'], password=os.environ['password'],
                      user=os.environ['user'], port=int(os.environ['port']), database=os.environ['database'], charset='utf8')


@tree.command(name="회원가입", description="회원가입입니다.")
async def register(interaction: Interaction, 영지명: str, 국가: ContryEnum):
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM info WHERE name = %s or id = %s",
                (영지명, interaction.user.id))
    flag = cur.fetchone()
    print(flag)
    if flag[0]:
        cur.close()
        return await interaction.response.send_message("이미 존재하는 영지명입니다.", ephemeral=True)
    embed = discord.Embed(title="회원가입", color=interaction.user.color)
    embed.add_field(name="영지명", value=영지명)
    embed.add_field(name="국가", value=국가.name)
    embed.set_footer(text="위 정보가 확실합니까? 국가와 영지명은 추후 변경할 수 없습니다.")
    view = ui.View(timeout=None)
    yes = ui.Button(style=ButtonStyle.green, label="예.")
    no = ui.Button(style=ButtonStyle.red, label="아니오.")

    async def yes_callback(interaction: Interaction):
        cur.execute("INSERT INTO info(id,name,contry) VALUES(%s,%s,%s)",
                    (interaction.user.id, 영지명, 국가.name))
        cur.execute("INSERT INTO inventory(id) VALUES(%s)",
                    (interaction.user.id,))
        for i in ["watertank", "bank", "powerstation", "restraunt", "town"]:
            cur.execute("INSERT INTO manifacture(id,name,last_claim) VALUES(%s,%s,%s)",
                        (interaction.user.id, i, datetime.datetime.now()))
        # cur.execute("INSERT INTO quest(id,type,item,key,value,amount)")
        con.commit()
        cur.close()
        await interaction.response.edit_message(content="생성이 완료되었습니다.", embed=None, view=None)
        await asyncio.sleep(5)
        await interaction.delete_original_response()

    async def no_callback(interaction: Interaction):
        cur.close()
        await interaction.delete_original_response()
    yes.callback = yes_callback
    no.callback = no_callback
    view.add_item(yes)
    view.add_item(no)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@tree.command(name="정보보기", description="유저 정보를 확인할 수 있습니다.")
async def viewInfo(interaction: Interaction, 유저: discord.User | None = None):
    if not 유저:
        embed = User(interaction.user.id).InfoEmbed()
        await interaction.response.send_message(embed, ephemeral=True)
    else:
        embed = User(유저.id).InfoEmbed()
        await interaction.response.send_message(embed, ephemeral=True)


@tree.command(name="영지관리", description="영지관리를 할 수 있습니다.")
async def managementTown(interaction: Interaction):

    dm_channel = await interaction.user.create_dm()
    if dm_channel:
        message = await dm_channel.send(content="패널을 생성중이에요!")
        await Pannel(interaction.user.id, message).setupMessage()
    else:
        await interaction.response.send_message("dm채널을 추가해 주세요!", ephemeral=True)


def exceptionHanlder(exc_type, exc_value, exc_tb):
    print(f"exc_type : {exc_type}")  # error type
    print(f"exc_type : {exc_value}")  # error message
    print(f"exc_type : {exc_tb}")  # trace_back


sys.excepthook = exceptionHanlder

client.run(os.environ["token"])
