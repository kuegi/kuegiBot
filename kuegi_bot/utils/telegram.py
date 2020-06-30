import requests
import threading

class TelegramBot:
	def __init__(self,logger,settings):
		self.token= settings.token
		self.logChatId= settings.logChatId
		self.signalChannel= settings.signalChannel
		self.logger= logger
		self.timer= None
		self.messagesToSend = {}

	def send_log(self,log_message,debounceId:str= None):
		if debounceId is None:
			debounceId= log_message
		if self.logChatId is None:
			self.logger.warn("missing telegram logChatId")
			return
		if self.timer is not None:
			self.timer.cancel()

		self.timer= threading.Timer(interval=5, function= self.__internal_send_logs)
		self.timer.start()
		self.messagesToSend[debounceId] = log_message

	def send_signal(self,signal_message):
		if self.signalChannel is not None:
			self.__internal_send(self.signalChannel,signal_message)

	def __internal_send_logs(self):
		for key, msg in self.messagesToSend.items():
			self.__internal_send(self.logChatId,msg)
		self.messagesToSend= {}
		self.timer= None

	def __internal_send(self,chat_id,message):
		if self.token is None:
			self.logger.warn("missing telegram token or chatId")
			return

		url = 'https://api.telegram.org/bot' + self.token + '/sendMessage?chat_id=' + chat_id+ '&text=' + message

		result= requests.get(url).json()
		if not result["ok"]:
			self.logger.warning("error sending telegram messages "+str(result))
	