# -*- coding: utf-8 -*-
# @Time   : 2021/9/20 22:21
# @Author : Gang
# @File   : ivDataProcessUtils.py
import numpy as np
from nptdms import TdmsFile
from gangLogger.myLog import MyLog
from ivAnalysisConst import *


class IVDataProcessUtils:
    logger = MyLog("IVDataProcessUtils", BASEDIR)

    @classmethod
    def loadTMDSFile(cls, filePath):
        """
        加载tdms文件（单个）
        :param file_path:tdms文件路径
        :return:采样电压（numpy）
        """
        with TdmsFile.open(filePath) as tdmsFile:
            biasVolt = tdmsFile.groups()[0].channels()[0][:]  # 此处读完数据就是numpy数组了
            current = tdmsFile.groups()[0].channels()[1][:]
            cond = tdmsFile.groups()[0].channels()[2][:]
        return [biasVolt, current, cond]

    @classmethod
    def hysteresis(cls, filePath, keyPara):
        biasVolt, current, cond = cls.loadTMDSFile(filePath)

        biasVTrace, currentTrace, condTrace = [], [], []
        diffBiasV = np.concatenate((np.diff(biasVolt), np.array([10.0])))
        startIdx = \
            np.where((biasVolt >= 0.099) & (biasVolt <= 0.101) & (diffBiasV >= 0.199) & (diffBiasV <= 0.201))[
                0] + 1

        endIdx0 = \
            np.where((biasVolt >= 0.199) & (biasVolt <= 0.201) & (diffBiasV >= -0.101) & (diffBiasV <= -0.099))[0][
                0]
        cyclePoint = endIdx0 - startIdx[0] + 50 if endIdx0 - startIdx[0] > 20000 else 30000

        # 确保扫描区间没有超过总长度，同时保证结束点的电压是0.1
        # strat是第一个为0.2的index  end是最后一个为0.2的点！！
        endIdx = startIdx + cyclePoint
        endIdx = endIdx[endIdx < biasVolt.shape[0]]  # 这里直接使用了布尔索引！！
        startIdx = startIdx[endIdx < biasVolt.shape[0]]
        biasVoltEnd = biasVolt[endIdx]
        tempIdx = np.where((biasVoltEnd >= 0.099) & (biasVoltEnd <= 0.101))[0]
        endIdx = endIdx[tempIdx]
        startIdx = startIdx[tempIdx]

        # 得到扫面区间，接下来就是把中间的切开！！
        for i in range(startIdx.shape[0]):
            biasVTrace.append(biasVolt[startIdx[i]:endIdx[i]])
            currentTrace.append(current[startIdx[i]:endIdx[i]])
            condTrace.append(cond[startIdx[i]:endIdx[i]])
        biasVTrace = np.array(biasVTrace)
        currentTrace = np.array(currentTrace)
        condTrace = np.array(condTrace)

        if biasVTrace.shape[0] == 0:
            return None, None, None

        # 寻找电压是0v的起始和终点
        quarterBiasV = round(0.35 * len(biasVTrace[0]))
        cutStart, cutEnd = np.ones(biasVTrace.shape[0], dtype=int), np.ones(biasVTrace.shape[0], dtype=int)
        if biasVTrace[0][quarterBiasV] < 0:
            for i in range(biasVTrace.shape[0]):
                for j in range(50, len(biasVTrace[i]) - 1):
                    if -0.0001 <= biasVTrace[i][j - 50] <= 0.0001 and biasVTrace[i][j + 1] < 0:
                        cutStart[i] = j
                        break
                if cutStart[i] == 1:
                    continue
                for j in range(cutStart[i] + 100, len(biasVTrace[i]) - 1):
                    if biasVTrace[i][j] >= 0 and biasVTrace[i][j + 1] < 0:
                        cutEnd[i] = j
                        break
        else:
            for i in range(biasVTrace.shape[0]):
                for j in range(50, len(biasVTrace[i]) - 1):
                    if -0.0001 <= biasVTrace[i][j - 50] <= 0.0001 and biasVTrace[i][j + 1] > 0:
                        cutStart[i] = j
                        break
                if cutStart[i] == 1:
                    continue
                for j in range(cutStart[i] + 100, len(biasVTrace[i]) - 1):
                    if biasVTrace[i][j] <= 0 and biasVTrace[i][j + 1] > 0:
                        cutEnd[i] = j
                        break

        # 删除bad boys
        trueIndex = np.where((cutStart == 1) | (cutEnd == 1), False, True)
        biasVTrace = biasVTrace[trueIndex]
        currentTrace = currentTrace[trueIndex]
        condTrace = condTrace[trueIndex]
        cutStart = cutStart[trueIndex]
        cutEnd = cutEnd[trueIndex]

        # 再次检查！！！
        if biasVTrace.shape[0] == 0:
            return None, None, None

        diffBiasTrace = np.concatenate(
            (np.diff(biasVTrace), np.array([10.0] * biasVTrace.shape[0]).reshape(biasVTrace.shape[0], -1)), axis=1)
        frontCheckBIdx = np.where(
            (biasVTrace >= 0.199) & (biasVTrace <= 0.201) & (diffBiasTrace >= -0.201) & (diffBiasTrace <= -0.199),
            True,
            False)
        backCheckFIdx = np.where(
            (biasVTrace >= -0.001) & (biasVTrace <= 0.001) & (diffBiasTrace >= 0.199) & (diffBiasTrace <= 0.201),
            True,
            False)
        backCheckBIdx = np.where(
            (biasVTrace >= 0.199) & (biasVTrace <= 0.201) & (diffBiasTrace >= -0.101) & (diffBiasTrace <= -0.099),
            True,
            False)

        # 此处对原来的程序做改动，此处应该应该对这三个check中的异常值进行删除
        trueIdx = np.apply_along_axis(np.any, 1, frontCheckBIdx) & np.apply_along_axis(np.any, 1,
                                                                                       backCheckFIdx) & np.apply_along_axis(
            np.any, 1, backCheckBIdx)
        """
        上面的写法，还可以这样写：
        eg:
        b=array([[1., 2., 3., 4.],
                [0., 0., 0., 0.],
                [0., 0., 0., 0.]])
        
        np.any(b,axis=1)
        Out[61]: array([ True, False, False])
        
        即np.any  np.all 都是可以指定axis这个轴参数的
        """
        biasVTrace = biasVTrace[trueIdx]
        currentTrace = currentTrace[trueIdx]
        condTrace = condTrace[trueIdx]
        cutStart = cutStart[trueIdx]
        cutEnd = cutEnd[trueIdx]
        frontCheckBIdx = frontCheckBIdx[trueIdx]
        backCheckFIdx = backCheckFIdx[trueIdx]
        backCheckBIdx = backCheckBIdx[trueIdx]

        # 再次检查！！！
        if biasVTrace.shape[0] == 0:
            return None, None, None

        frontCheckB = np.array([np.where(temp)[0][0] for temp in frontCheckBIdx])
        backCheckF = np.array([np.where(temp)[0][0] for temp in backCheckFIdx])
        backCheckB = np.array([np.where(temp)[0][0] for temp in backCheckBIdx])

        # 其实这里我担心是有问题的，因为万一frontCheckB[i]-100比100 还小呢。。。。就离谱了
        condCheckF = np.array([np.mean(condTrace[i][100:frontCheckB[i] - 100]) for i in range(biasVTrace.shape[0])])
        condCheckB = np.array(
            [np.mean(condTrace[i][backCheckF[i] + 100:backCheckB[i] - 100]) for i in range(biasVTrace.shape[0])])

        # 通过偏压把电导曲线切出来
        # 注意这里的这几个data其中每一行的数据维度都是不一致的！
        biasVData = np.empty(biasVTrace.shape[0], dtype=object)
        currentData = np.empty(biasVTrace.shape[0], dtype=object)
        condData = np.empty(biasVTrace.shape[0], dtype=object)

        for i in range(biasVTrace.shape[0]):
            biasVData[i] = biasVTrace[i, cutStart[i]:cutEnd[i]]
            currentData[i] = currentTrace[i, cutStart[i]:cutEnd[i]]
            condData[i] = condTrace[i, cutStart[i]:cutEnd[i]]

        # 删除超过scanRange的数据
        scanRange = keyPara["le_ScanRange"]
        trueIdx = [(data <= scanRange).all() for data in biasVData]
        biasVData = biasVData[trueIdx]
        currentData = currentData[trueIdx]
        condData = condData[trueIdx]
        condCheckB = condCheckB[trueIdx]
        condCheckF = condCheckF[trueIdx]

        # 再次检查！！！
        if biasVData.shape[0] == 0:
            return None, None, None

        # 整流判定  这个一般是不用开启的！！！
        selectRetificate = keyPara["le_SelectRetificate"]
        if selectRetificate == 0:
            retificationCheckGF = np.zeros(biasVData.shape[0])
            retificationCheckGB = np.zeros(biasVData.shape[0])
            quarterBiasV = round(0.35 * len(biasVTrace[0]))
            if biasVTrace[0][quarterBiasV] < 0:
                for i in range(biasVData.shape[0]):
                    retificationCheckGF = np.mean(
                        condData[i][(biasVData >= -scanRange - 0.001) & (biasVData <= -scanRange + 0.001)])
                    retificationCheckGB = np.mean(
                        condData[i][(biasVData >= scanRange - 0.001) & (biasVData <= scanRange + 0.001)])
            else:
                for i in range(biasVData.shape[0]):
                    retificationCheckGB = np.mean(
                        condData[i][(biasVData >= -scanRange - 0.001) & (biasVData <= -scanRange + 0.001)])
                    retificationCheckGF = np.mean(
                        condData[i][(biasVData >= scanRange - 0.001) & (biasVData <= scanRange + 0.001)])

            biasVData = np.where(retificationCheckGF >= retificationCheckGB, -biasVData, biasVData)
        # 完成整流判定

        # 对电流进行处理
        for i in range(currentData.shape[0]):
            currentData[i] = np.log10(currentData[i]) + 6
            currentData[i] = np.where(currentData[i] == -np.inf, -3, currentData[i])

        # 判断是否处于悬停状态
        peakStart = keyPara["le_PeakStart"]
        peakEnd = keyPara["le_PeakEnd"]
        trueIdx = np.where(
            (condCheckB >= peakEnd) & (condCheckB <= peakStart) & (condCheckF >= peakEnd) & (
                    condCheckF <= peakStart),
            True, False)
        currentData = currentData[trueIdx]
        condData = condData[trueIdx]
        biasVData = biasVData[trueIdx]

        # 再次检查！！！
        if biasVData.shape[0] == 0:
            return None, None, None
        else:
            return currentData, condData, biasVData

    @classmethod
    def getPartitionData(cls, currentData, condData, biasVData):

        """
        在matlab的版本里面，还要将数据叠加成矩阵，然后再绘图，这里我认为不再需要这样操作！直接hisd2d绘图就可以了！！
        另外此处应该将数据扁平化处理！！
        """

        i = 0
        length = biasVData[i].shape[0]
        pointA = round(0.25 * length)
        pointB = round(0.75 * length)
        # 正向扫描数据提取
        biasVDataFor = biasVData[i][pointA:pointB]
        currentDataFor = currentData[i][pointA:pointB]
        condDataFor = condData[i][pointA:pointB]
        # 反向扫描数据提取
        biasVDataReve = np.concatenate((biasVData[i][:pointA], biasVData[i][pointB:]))
        currentDataReve = np.concatenate((currentData[i][:pointA], currentData[i][pointB:]))
        condDataReve = np.concatenate((condData[i][:pointA], condDataFor[i][pointB:]))

        if biasVData.shape[0] == 1:
            return biasVDataFor, currentDataFor, condDataFor, biasVDataReve, currentDataReve, condDataReve
        # 说明有效的不止一个开始展平
        for i in range(1, biasVData.shape[0]):
            length = biasVData[i].shape[0]
            pointA = round(0.25 * length)
            pointB = round(0.75 * length)
            # 正向扫描数据叠加
            biasVDataFor = np.concatenate((biasVDataFor, biasVData[i][pointA:pointB]))
            currentDataFor = np.concatenate((currentDataFor, currentData[i][pointA:pointB]))
            condDataFor = np.concatenate((condDataFor, condData[i][pointA:pointB]))

            # 反向扫描数据叠加
            biasVDataReve = np.concatenate(
                (biasVDataReve, np.concatenate((biasVData[i][:pointA], biasVData[i][pointB:]))))
            currentDataReve = np.concatenate(
                (currentDataReve, np.concatenate((currentData[i][:pointA], currentData[i][pointB:]))))
            condDataReve = np.concatenate(
                (condDataReve, np.concatenate((condData[i][:pointA], condData[i][pointB:]))))

        return biasVDataFor, currentDataFor, condDataFor, biasVDataReve, currentDataReve, condDataReve