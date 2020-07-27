import requests
import threading

class TelegramBot:
	def __init__(self,logger,settings):
		self.token= settings.token
		self.logChatId= settings.logChatId
		self.executionChannel= settings.executionChannel
		self.logger= logger
		self.timer= None
		self.messagesToSend = {}

	def send_log(self,log_message,debounceId:str= None):
		if self.logChatId is None:
			self.logger.warn("missing telegram logChatId")
			return

		self.__internal_send(self.logChatId, log_message)
		''' 
		# if doing debounce, but might have problems with id collision on multiple ids
		if debounceId is None:
			debounceId= log_message
		if self.timer is not None:
			self.timer.cancel()

		self.timer= threading.Timer(interval=35, function= self.__internal_send_logs)
		self.timer.start()
		self.messagesToSend[debounceId] = log_message
		'''

	def send_execution(self, signal_message):
		if self.executionChannel is not None:
			self.__internal_send(self.executionChannel, signal_message)

	def __internal_send_logs(self):
		self.timer= None
		for key, msg in self.messagesToSend.items():
			self.__internal_send(self.logChatId,msg)
		self.messagesToSend= {}

	def __internal_send(self,chat_id,message):
		if self.token is None:
			self.logger.warn("missing telegram token or chatId")
			return

		url = 'https://api.telegram.org/bot' + self.token + '/sendMessage?chat_id=' + chat_id+ '&text=' + message

		result= requests.get(url).json()
		if not result["ok"]:
			self.logger.warning("error sending telegram messages "+str(result))
	